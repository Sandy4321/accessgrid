
import wx

from AccessGrid import Log
from AccessGrid.Events import Event
from AccessGrid.Platform import IsWindows, Config
from AccessGrid.ClientProfile import ClientProfile
from AccessGrid.Toolkit import WXGUIApplication
from AccessGrid.SharedAppClient import SharedAppClient
from AccessGrid.Platform.Config import UserConfig

import os
import getopt
from time import localtime , strftime

log = Log.GetLogger(Log.AppMonitor)

class AppMonitor:
    '''
    An Application Monitor connects to an Application Service and
    displays current application state such as participants and their status,
    application name, and description. It also includes an event window
    that shows when participants joined, data changed, and so forth.
    '''
 
    def __init__(self, parent, appUrl):
        '''
        Opens the Application Monitor frame and loads it with
        current application state. Also, register callbacks for
        events that updates the state.
        
        **Arguments**
        *parent* Parent frame
        *appUrl* The URL to the application service
        '''
        self.participants = {}

        # Create UI frame
        self.frame = AppMonitorFrame(parent, -1, "Application Monitor", self)
                
        # Create application client. Use Log.VenueClient to make sure log output
        # is sent to correct file.
        self.sharedAppClient = SharedAppClient(Log.VenueClient)
        self.log = self.sharedAppClient.InitLogging()
                             
        # Join the application session
        self.sharedAppClient.Join(appUrl)
      
        # Register callbacks
        self.RegisterCallbacks()
        
        # Connect to application and get state info
        self.GetApplicationInfo()
        
        if self.frame:
            self.frame.Show()

    def RegisterCallbacks(self):
        '''
        Register methods called when the application service distributes
        an event
        '''
        self.sharedAppClient.RegisterEventCallback(Event.APP_PARTICIPANT_JOIN, self.ParticipantJoined)
        self.sharedAppClient.RegisterEventCallback(Event.APP_PARTICIPANT_LEAVE, self.ParticipantLeft)
        self.sharedAppClient.RegisterEventCallback(Event.APP_SET_DATA, self.SetData)
        self.sharedAppClient.RegisterEventCallback(Event.APP_UPDATE_PARTICIPANT, self.UpdateParticipant)

    #
    # Callbacks. Every UI access have to be made by using wx.CallAfter.
    #
        
    def ParticipantJoined(self, event):
        '''
        This method is called when a new participant joined the application session.
        '''
        appParticipantDescription = event.data
        wx.CallAfter(self.frame.AddParticipant, appParticipantDescription)
                
    def ParticipantLeft(self, event):
        '''
        This method is called when a participant left the application session.
        '''
        appParticipantDescription = event.data
        wx.CallAfter(self.frame.RemoveParticipant, appParticipantDescription)

    def SetData(self, event):
        '''
        This method is called when data changed in application service.
        '''
        appDataDescription = event.data
        wx.CallAfter(self.frame.AddData, appDataDescription)

    def UpdateParticipant(self, event):
        '''
        This method is called when a participant changed profile or status.
        '''
        
        appParticipantDescription = event.data
        wx.CallAfter(self.frame.UpdateParticipant, appParticipantDescription)

    #
    # ----- Callbacks end.
    #
    
    def ShutDown(self):
        '''
        Stop event client and leave the application session.
        '''
        self.sharedAppClient.Shutdown()
                       
    def GetApplicationInfo(self):
        '''
        Get state from applicaton service and update UI frame.
        '''
        appState = self.sharedAppClient.GetApplicationState() 
        participants = self.sharedAppClient.GetParticipants()
        dataKeys = self.sharedAppClient.GetDataKeys()

        # Set participants
        for appParticipantDesc in participants:
            self.frame.AddInitParticipant(appParticipantDesc)

        dataDict = {}
        for key in dataKeys:
            data = self.sharedAppClient.GetData(key)
            dataDict[key] = data

        self.frame.AddInitData(dataDict)
                      
        # Set application information
        self.frame.SetName(appState.name)
        self.frame.SetDescription(appState.description)

        
class AppMonitorFrame(wx.Frame):
    '''
    The AppMonitor Frame includes all user interface components for the
    Application Monitor.
    '''

    ID_WINDOW_TOP = wx.NewId()
    ID_WINDOW_BOTTOM = wx.NewId()
    
    def __init__(self, parent, id, title, appMonitor, **kw):
        wx.Frame.__init__(self, parent, id, title, **kw)
        self.appMonitor = appMonitor

        # upper sash window
        self.topWindow = wx.SashLayoutWindow(self, self.ID_WINDOW_TOP,
                                            wx.DefaultPosition)
        self.topWindow.SetOrientation(wx.LAYOUT_HORIZONTAL)
        self.topWindow.SetAlignment(wx.LAYOUT_TOP)
        self.topWindow.SetSashVisible(wx.SASH_BOTTOM, TRUE)
        self.topWindow.SetExtraBorderSize(2)
        
        # lower sash window
        self.bottomWindow = wx.SashLayoutWindow(self, self.ID_WINDOW_BOTTOM,
                                               wx.DefaultPosition)
        self.bottomWindow.SetOrientation(wx.LAYOUT_HORIZONTAL)
        self.bottomWindow.SetAlignment(wx.LAYOUT_BOTTOM)
        self.bottomWindow.SetExtraBorderSize(2)
                      
        # widgets for upper sash window
        self.panelTop = wx.Panel(self.topWindow, -1, wx.DefaultPosition,
                                wx.DefaultSize)
        self.nameText = wx.StaticText(self.panelTop, -1,
                                     "This is the name",
                                     style = wx.ALIGN_CENTER)
        font = wx.Font(wx.DEFAULT, wx.NORMAL, wx.NORMAL, wx.BOLD)
        self.nameText.SetFont(font)

        self.descriptionText = wx.StaticText(self.panelTop, -1,
                                            "No description",
                                            size = wx.Size(10,40))
        self.partListCtrl = wx.ListCtrl(self.panelTop, -1,
                                       style = wx.LC_REPORT)
        self.partListCtrl.InsertColumn(0, "Participants")
        self.partListCtrl.InsertColumn(1, "Status")

        # widgets for lower sash window
        self.panelBottom = wx.Panel(self.bottomWindow, -1,
                                   wx.DefaultPosition, wx.DefaultSize)
        self.textCtrl = wx.TextCtrl(self.panelBottom, -1,
                                   style = wx.TE_MULTILINE |
                                   wx.TE_READONLY | wx.TE_RICH)
        
        self.idToProfile = {}
        self.profileToId = {}

        self.idToData = {}
        self.dataToId = {}
        
        self.__setEvents()
        self.__layout()

        # finally set size to get proper layout
        self.SetSize(wx.Size(400,400))
        self.topWindow.SetDefaultSize(wx.Size(200, 200))

        

    def OnSashDrag(self, event):
        '''
        Called when a sash window has been dragged.
        '''
        
        if event.GetDragStatus() == wx.SASH_STATUS_OUT_OF_RANGE:
            return
        
        id = event.GetId()
        if id == self.ID_WINDOW_TOP:
            self.topWindow.SetDefaultSize(wx.Size(1000, event.GetDragRect().height))
                    
        wx.LayoutAlgorithm().LayoutWindow(self)
              
    def OnSize(self, event):
        """
        Sets correct column widths.
        """
        wx.LayoutAlgorithm().LayoutWindow(self)

        w = self.partListCtrl.GetClientSize().width
        self.partListCtrl.SetColumnWidth(0, w*(0.50) )
        self.partListCtrl.SetColumnWidth(1, w*(0.50) )

    def OnExit(self, event):
        '''
        Called when window is closed.
        '''
        self.appMonitor.ShutDown()
        
        self.Destroy()

    def ShowMessage(self, message):
        '''
        Shows a message dialog
        '''
        messageDialog = wx.MessageDialog(None, message, "Application Monitor", style = wx.OK|wx.ICON_INFORMATION)
        messageDialog.ShowModal()
        messageDialog.Destroy()
                
    def SetName(self, name):
        '''
        Set application name.
        '''
        self.nameText.SetLabel(name)

    def SetDescription(self, desc):
        '''
        Set application description.
        '''
        self.descriptionText.SetLabel(desc)

    def AddParticipant(self, pDesc):
        '''
        Adds participant to list and displays an event message.
        '''

        # Ignore participants without client profile (a monitor for example)
        if pDesc.clientProfile == "None" or pDesc.clientProfile == None:
            return
        
        self.AddInitParticipant(pDesc)
        
        # Add event text
        message = pDesc.clientProfile.name + " joined this session "
        
        # Add time to event message
        dateAndTime = strftime("%a, %d %b %Y, %H:%M:%S", localtime() )
        message = message + " ("+dateAndTime+")" 
        
        # Events are coloured blue
        self.textCtrl.SetDefaultStyle(wx.TextAttr(wx.BLUE))
        self.textCtrl.AppendText(message+'\n')
        self.textCtrl.SetDefaultStyle(wx.TextAttr(wx.BLACK))

        self.__SetRightScroll()
                        
    def AddInitParticipant(self, pDesc):
        """
        Add a participant to the list. Initially done when connecting to a
        service. No event message is displayed.
        """
        
        # Ignore participants without client profile (a monitor for example)
        if pDesc.clientProfile == "None" or pDesc.clientProfile == None:
            return

        idx = self.partListCtrl.GetItemCount()

        self.idToProfile[idx] = pDesc
        self.profileToId[pDesc.appId] = idx
        
        self.partListCtrl.InsertStringItem(idx, pDesc.clientProfile.name)
        self.partListCtrl.SetStringItem(idx, 1, pDesc.status)
        self.partListCtrl.SetItemData(idx, idx)
        
        wx.LayoutAlgorithm().LayoutWindow(self)

    def RemoveParticipant(self, pDesc):
        '''
        Remove a participant.
        '''
        if self.profileToId.has_key(pDesc.appId):
            id = self.profileToId[pDesc.appId]
            
            item = self.partListCtrl.FindItemData(-1, id)
        
            self.partListCtrl.DeleteItem(item)

            #Add event text
            message = pDesc.clientProfile.name + " left this session "
            
            # Add time to event message
            dateAndTime = strftime("%a, %d %b %Y, %H:%M:%S", localtime() )
            message = message + " ("+dateAndTime+")" 
            
            # Events are coloured blue
            self.textCtrl.SetDefaultStyle(wx.TextAttr(wx.BLUE))
            self.textCtrl.AppendText(message+'\n')
            self.textCtrl.SetDefaultStyle(wx.TextAttr(wx.BLACK))

            self.__SetRightScroll()

    def GetProfile(self, appId):
        '''
        Converts applicaiton ID to client profile.
        '''
        if not self.profileToId.has_key(appId):
            return None

        id = self.profileToId[appId]

        if not self.idToProfile.has_key(id):
            return None
                
        profile = self.idToProfile[id]

        return profile
        
    def UpdateParticipant(self, pDesc):
        """
        Update a participant.
        """
        # Ignore participants without client profile (a monitor for example)
        if pDesc.clientProfile == "None":
            return
                       
        if self.profileToId.has_key(pDesc.appId):
            id = self.profileToId[pDesc.appId]
            
            self.partListCtrl.SetStringItem(id, 0, pDesc.clientProfile.name)
            self.partListCtrl.SetStringItem(id, 1, pDesc.status)
            
    def AddData(self, appDataDesc):
        '''
        Print data event in text window.
        '''
        appProfile = self.GetProfile(appDataDesc.appId)
        
        # Ignore participants without client profile (a monitor for example)
        if appProfile == None:
            return

        name = appProfile.clientProfile.name
        text = name+" changed: "+str(appDataDesc.key) + " = " + str(appDataDesc.value) + '\n'
        self.textCtrl.AppendText(text)

        self.__SetRightScroll()

    def AddInitData(self, dataDict):
        """
        Display data text in event window. Initially done when connecting to service. No time
        stamp is included in text.
        """
        # Data is coloured red
        self.textCtrl.SetDefaultStyle(wx.TextAttr(wx.RED))
       
        for key in dataDict.keys():
            text = str(key) + "=" + str(dataDict[key]) + '\n'
            self.textCtrl.AppendText(text)
            
            #self.__SetRightScroll()

        self.textCtrl.SetDefaultStyle(wx.TextAttr(wx.BLACK))
        
    def __SetRightScroll(self):
        '''
        Scrolls to right position in text output field 
        '''

        if IsWindows():
            # Added due to wx.Python bug. The wx.TextCtrl doesn't
            # scroll properly when the wx.TE_AUTO_URL flag is set.
            self.textCtrl.ScrollLines(-1)
                                        
    def __setEvents(self):
        '''
        Initialize events.
        '''

        wx.EVT_SASH_DRAGGED_RANGE(self, self.ID_WINDOW_TOP, self.ID_WINDOW_BOTTOM, self.OnSashDrag)
        wx.EVT_SIZE(self, self.OnSize)
        
        wx.EVT_CLOSE(self, self.OnExit)
    
    def __layout(self):
        '''
        Handles UI layout.
        '''
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        vs = wx.BoxSizer(wx.VERTICAL)
      
        vs.Add(self.nameText, 0, wx.EXPAND | wx.ALL, 4)
        
        vs.Add(self.descriptionText, 0, wx.EXPAND | wx.ALL, 4)
        vs.Add(wx.StaticLine(self.panelTop, -1), 0, wx.EXPAND)
        vs.Add((5,5))
        vs.Add(self.partListCtrl, 2, wx.EXPAND | wx.ALL, 4)

        sizer.Add(vs, 1, wx.EXPAND|wx.ALL, 5)

        sizer2 = wx.BoxSizer(wx.VERTICAL)
        sizer2.Add(self.textCtrl, 1, wx.EXPAND | wx.ALL, 8)
               
        self.panelTop.SetSizer(sizer)
        sizer.Fit(self.panelTop)
        self.panelTop.SetAutoLayout(1)
        
        self.panelTop.Refresh()

        self.panelBottom.SetSizer(sizer2)
        sizer2.Fit(self.panelBottom)
        self.panelBottom.SetAutoLayout(1)
        self.panelBottom.Layout()

        wx.LayoutAlgorithm().LayoutWindow(self, self.panelTop)
                       
def SetLogging():
    logFile = None
    debugMode = 1
    
    if logFile is None:
        logname = os.path.join(UserConfig.instance().GetConfigDir(),
                               "NodeSetupWizard.log")
    else:
        logname = logFile
        
    hdlr = Log.FileHandler(logname)
    hdlr.setFormatter(Log.GetFormatter())
    Log.HandleLoggers(hdlr, Log.GetDefaultLoggers())
    
    if debugMode:
        hdlr = Log.StreamHandler()
        hdlr.setFormatter(Log.GetLowDetailFormatter())
        Log.HandleLoggers(hdlr, Log.GetDefaultLoggers())


class ArgumentManager:
    def __init__(self):
        self.debugMode = 0
        self.argDict = {}
        self.argDict['appUrl'] = None
      
    def GetArguments(self):
        return self.argDict
        
    def Usage(self):
        """
        How to use the program.
        """
        print "%s:" % (sys.argv[0])
        print "  -a|--appUrl: Application URL"
        print "  -h|--help: print usage"
            
    def ProcessArgs(self):
        """
        Handle any arguments we're interested in.
        """
        try:
            opts, args = getopt.getopt(sys.argv[1:], "a:h",
                                       ["appUrl=", "help"])

        except getopt.GetoptError:
            self.Usage()
            sys.exit(2)
            
        for opt, arg in opts:
            if opt in ('-h', '--help'):
                self.Usage()
                sys.exit(0)
            
            elif opt in ('-a', '--appUrl'):
                self.argDict['appUrl'] = arg


        if not self.argDict['appUrl']:
            self.Usage()
            sys.exit(0)
        
if __name__ == "__main__":
    SetLogging()
    am = ArgumentManager()
    am.ProcessArgs()
    arguments = am.GetArguments()

    appUrl = arguments['appUrl']
    
    pp = wx.PySimpleApp()
    monitor = AppMonitor(None, appUrl)
    
    pp.MainLoop()
