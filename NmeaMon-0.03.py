#!/usr/bin/env python

# Copyright (C) 2010 by Will Kamp <manimaul!gmail.com>
# Published under the terms of "Simplified BSD License".
# License text available at http://opensource.org/licenses/bsd-license.php

import wx, os, serial, threading, gps, time, commands

#----------------------------------------------------------------------
# Create an own event type, so that GUI updates can be delegated
# this is required as on some platforms only the main thread can
# access the GUI without crashing. wxMutexGuiEnter/wxMutexGuiLeave
# could be used too, but an event is more elegant.

SERIALRX = wx.NewEventType()
# bind to serial data receive events
EVT_SERIALRX = wx.PyEventBinder(SERIALRX, 0)

class SerialRxEvent(wx.PyCommandEvent):
    eventType = SERIALRX
    def __init__(self, windowID, data):
        wx.PyCommandEvent.__init__(self, self.eventType, windowID)
        self.data = data

    def Clone(self):
        self.__class__(self.GetId(), self.data)
#----------------------------------------------------------------------

SerDevLs = [] #List of serial devices

def SerialCheck(dev):
    num = 0
    for _ in range(99):
        s = dev + str(num)
        d = os.path.exists(s)
        if d == True:
            SerDevLs.append(s)      
        num = num + 1
        
#Check for Serial devices and put in SerDevLs list
SerialCheck('/dev/rfcomm')
SerialCheck('/dev/ttyUSB')
SerialCheck('/dev/ttyS')

#If gpsd exists in path add it to device list
def progExist(prog):
    exist = False
    pathlist = os.environ['PATH'].split(os.pathsep)
    for _ in pathlist:
        s = str(_) + '/' + prog
        d = os.path.exists(s)
        if d == True:
            exist = True
    if exist == True:
        return True
    else:
        return False
    
if progExist('gpsd') == True:
    SerDevLs.append('gpsd @ localhost:2947')

class Form(wx.Panel):
    def __init__(self, *args, **kwargs):
        super(Form, self).__init__(*args, **kwargs)
        self.serial = serial.Serial()
        self.serial.timeout = 0.5   #make sure that the alive event can be checked from time to time
        #self.settings = TerminalSetup() #placeholder for the settings
        self.thread = None
        self.alive = threading.Event() 
        self.devices = SerDevLs
        self.SerDev = SerDevLs[0]
        self.SerBaud = '4800'
        self.bauds = ['2400', '4800', '9600', '19200', '38400', '57600', '115200']
        self.createControls()
        self.bindEvents()
        self.doLayout()
        if not self.alive.isSet():
            self.Close()
  
    def StartThread(self, fThread):
        """Start the receiver thread"""
        #print fThread   
        self.thread = threading.Thread(target=fThread)
        self.thread.setDaemon(1)
        self.alive.set()
        self.thread.start()
        self.checkButton.SetLabel('Pause')
        self.checkButton.Bind(wx.EVT_BUTTON, self.onCheckOff)

    def StopThread(self):
        """Stop the receiver thread, wait util it's finished."""
        if self.thread is not None:
            self.alive.clear()          #clear alive event for thread
            self.thread.join()          #wait until thread has finished
            self.thread = None
            self.checkButton.SetLabel('Start')
            self.checkButton.Bind(wx.EVT_BUTTON, self.onCheck)

    def createControls(self):
        self.logger = wx.TextCtrl(self, -1, "", style=wx.TE_MULTILINE|wx.TE_READONLY)
        self.deviceLabel = wx.StaticText(self, label="NMEA Data Source")
        self.baudLabel = wx.StaticText(self, label="Baud Rate")
        self.deviceComboBox = wx.ComboBox(self, choices=self.devices, style=wx.CB_DROPDOWN)
        self.deviceComboBox.SetValue(self.SerDev)
        self.baudComboBox = wx.ComboBox(self, choices=self.bauds, style=wx.CB_READONLY)
        self.baudComboBox.SetValue('4800')
        self.checkButton = wx.Button(self, label= "Start", style=wx.ID_OK)
        self.clearButton = wx.Button(self, label= "Clear Result", style=wx.ID_OK)
        self.logLabel = wx.StaticText(self, label = "Connected to port: None | Ready to start")

    def bindEvents(self):
        self.deviceComboBox.Bind(wx.EVT_COMBOBOX, self.onDeviceEntered)
        self.deviceComboBox.Bind(wx.EVT_TEXT, self.onDeviceEntered)
        self.baudComboBox.Bind(wx.EVT_COMBOBOX, self.onBaudEntered)
        self.baudComboBox.Bind(wx.EVT_TEXT, self.onBaudEntered)
        self.clearButton.Bind(wx.EVT_BUTTON, self.__logClear)
        self.checkButton.Bind(wx.EVT_BUTTON, self.onCheck)
        self.Bind(EVT_SERIALRX, self.OnSerialRead)

    def doLayout(self):
        ''' Layout the controls that were created by createControls(). 
            Form.doLayout() will raise a NotImplementedError because it 
            is the responsibility of subclasses to layout the controls. '''
        raise NotImplementedError

    # Callback methods:
    def onDeviceEntered(self, event):
        self.SerDev = event.GetString()
        if self.SerDev == 'gpsd @ localhost:2947':
            self.baudComboBox.Enable(False)
            self.deviceComboBox.SetEditable(False)
#            self.baudComboBox.SetItems([])
#            self.SerBaud = '127.0.0.1:2947'
#            self.baudComboBox.SetValue('127.0.0.1:2947')
#            self.baudComboBox.SetEditable(True)
        else:
            self.baudComboBox.Enable(True)
            self.deviceComboBox.SetEditable(True)
#            self.baudComboBox.SetItems(self.bauds)
#            self.SerBaud = '4800'
#            self.baudComboBox.SetValue(self.SerBaud)
#            self.baudComboBox.SetEditable(False)

    def onBaudEntered(self, event):
        self.SerBaud = event.GetString()

    def onCheck(self,event):
        if self.SerDev == 'gpsd @ localhost:2947':
            if self.procRunning('gpsd') == True:
                self.Status('Connected to gpsd @ 127.0.0.1:2947')
                self.StartThread(self.GpsdMonThreadRaw)
            else:
                self.Status('sorry, gpsd is not running\n')                
        else:
            self.Status('Connected to: ' + self.SerDev + ' Baud: ' + self.SerBaud)
            self.Feed('')
            self.StartThread(self.PortMonThread)
    
    def onCheckOff(self, event):
        self.Status('Connected to port: None | Ready to start')
        self.StopThread()
        
    def OnSerialRead(self, event):
        """Handle input from the serial port."""
        text = event.data
        self.logger.AppendText(text)
        
    def PortMonThread(self):
        SerBaud = int(self.SerBaud)
        SerNMEA = serial.Serial(self.SerDev, SerBaud, timeout=0.5)
        while self.alive.isSet():
            text = SerNMEA.read(1) #reads 1 byte
            if text:
                n = SerNMEA.inWaiting()     #look if there is more to read
                if n:
                    text = text + SerNMEA.read(n) #get it
                text = text.replace('\r', '')
                event = SerialRxEvent(self.GetId(), text)
                self.GetEventHandler().AddPendingEvent(event)
        self.Feed('\n')
        
    def procRunning(self,proc):
        cmd = 'pidof ' + proc
        if commands.getstatusoutput(cmd)[0] == 256:
            return False
        else:
            return True
        
    def GpsdMonThreadRaw(self):
        session = gps.gps()  
        while self.alive.isSet():
            session.query("$")
            text = str(session.timings)
            text = text.replace('\t', ',')
            event = SerialRxEvent(self.GetId(), text)
            self.GetEventHandler().AddPendingEvent(event)
            time.sleep(.1)
            
    def GpsdMonThread(self): #This causes an error that needs to be fixed
        session = gps.gps()
        while self.alive.isSet():
            session.query("admosy")
            text = 'Latitude = ' + str(session.fix.latitude) + '\r'
            event = SerialRxEvent(self.GetId(), text)
            self.GetEventHandler().AddPendingEvent(event)
            text = 'Longitude = ' + str(session.fix.longitude) + '\r'
            event = SerialRxEvent(self.GetId(), text)
            self.GetEventHandler().AddPendingEvent(event)
            text = 'UTC = ' + str(session.utc) + '\r'
            event = SerialRxEvent(self.GetId(), text)
            self.GetEventHandler().AddPendingEvent(event)
#            session.fix.altitude
#            session.fix.eph
#            session.fix.epv
#            session.fix.ept
#            session.fix.speed
#            session.fix.climb
            time.sleep(.1)
            self.logger.Clear()

    # Helper method(s):
    def Feed(self, message):
        ''' Private method to append a string to the logger text control. '''
        self.logger.AppendText('%s\n'%message)
        
    def Status(self, message):
        self.logLabel.SetLabel(message)
    
    def __logClear(self, message):
        self.logger.Clear()

class FormWithSizer(Form):
    def doLayout(self):
        ''' Layout the controls by means of sizers. '''

        # A horizontal BoxSizer will contain the GridSizer (on the left)
        # and the logger text control (on the right):
        boxSizer = wx.BoxSizer(orient=wx.VERTICAL)
        # A GridSizer will contain the other controls:
        gridSizer = wx.FlexGridSizer(rows=2, cols=2, vgap=10, hgap=10)
        igridSizer = wx.FlexGridSizer(rows=1, cols=2, vgap=10, hgap=10)

        # Prepare some reusable arguments for calling sizer.Add():
        expandOption = dict(flag=wx.EXPAND)
        noOptions = dict()
        emptySpace = ((0, 0), noOptions)
        
        # Add the controls to the sizers:
        for control, options in \
            [(self.clearButton, dict(flag=wx.ALIGN_CENTER)), 
             (self.checkButton, dict(flag=wx.ALIGN_CENTER))]:
            igridSizer.Add(control, **options)
            
        for control, options in \
            [(self.deviceLabel, noOptions), 
             (self.deviceComboBox, expandOption),
             (self.baudLabel, noOptions), 
             (self.baudComboBox, expandOption),
             emptySpace, (igridSizer, dict(border=0, flag=wx.ALL))]:
            gridSizer.Add(control, **options)

        for control, options in \
            [(gridSizer, dict(border=5, flag=wx.ALL)),
             (self.logLabel, noOptions),
             (self.logger, dict(border=5, flag=wx.ALL|wx.EXPAND, proportion=1))]:
            boxSizer.Add(control, **options)

        self.SetSizerAndFit(boxSizer)

if __name__ == '__main__':
    app = wx.App(0)
    frame = wx.Frame(None, pos=(-1, -1), size=(600, 300))
    panel = FormWithSizer(frame)
    frame.Show()
    app.MainLoop()
