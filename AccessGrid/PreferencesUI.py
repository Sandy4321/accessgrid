import os

from AccessGrid import Log
from AccessGrid.Platform import IsOSX
from AccessGrid.Preferences import Preferences
from AccessGrid.Platform.Config import AGTkConfig

from wxPython.wx import *
import  wx.lib.intctrl

log = Log.GetLogger(Log.VenueClient)

class PreferencesDialog(wxDialog):
    ID_WINDOW_LEFT = 0
    ID_WINDOW_RIGHT = 1
    
    def __init__(self, parent, id, title, preferences):
        '''
        Initialize ui components and events.
        '''
        wxDialog.__init__(self, parent, id, title,
                          style = wxRESIZE_BORDER | wxDEFAULT_DIALOG_STYLE,
                          size = wxSize(550, 350))
        self.Centre()
       
      
        self.sideWindow = wxSashWindow(self, self.ID_WINDOW_LEFT,
                                       wxDefaultPosition,
                                       wxSize(150, -1))

        self.sideWindow.SetSashVisible(wxSASH_RIGHT, TRUE)
        
        self.preferencesWindow = wxSashWindow(self, self.ID_WINDOW_RIGHT,
                                              wxDefaultPosition,
                                              wxSize(200, -1))
        self.sideTree = wxTreeCtrl(self.sideWindow, wxNewId(), wxDefaultPosition, 
                                   wxDefaultSize, style = wxTR_HIDE_ROOT)
        self.okButton = wxButton(self, wxID_OK, "Save")
        self.cancelButton = wxButton(self, wxID_CANCEL, "Close")
        self.preferences = preferences

        # Create panels for preferences
        self.preferencesPanel = wxPanel(self.preferencesWindow, wxNewId(),
                                        style = wxSUNKEN_BORDER)
        self.title = wxTextCtrl(self.preferencesPanel, wxNewId(), "TITLE",
                                style = wxTE_READONLY | wxTE_CENTRE )
        self.nodePanel = NodePanel(self.preferencesPanel, wxNewId(),
                                         self.preferences)
        self.profilePanel = ProfilePanel(self.preferencesPanel, wxNewId(),
                                         self.preferences)
        self.loggingPanel = LoggingPanel(self.preferencesPanel, wxNewId(),
                                         self.preferences)
        self.venueConnectionPanel = VenueConnectionPanel(self.preferencesPanel, wxNewId(),
                                         self.preferences)
        self.networkPanel = NetworkPanel(self.preferencesPanel, wxNewId(),
                                         self.preferences)
        self.navigationPanel = NavigationPanel(self.preferencesPanel, wxNewId(),
                                               self.preferences)
        self.loggingPanel.Hide()
        self.venueConnectionPanel.Hide()
        self.networkPanel.Hide()
        self.navigationPanel.Hide()
        self.nodePanel.Hide()
        self.currentPanel = self.loggingPanel

        EVT_SASH_DRAGGED(self.sideWindow, self.ID_WINDOW_LEFT, self.__OnSashDrag)
        EVT_TREE_SEL_CHANGED(self, self.sideTree.GetId(), self.OnSelect)
                       
        self.__Layout()
        self.__InitTree()

        if IsOSX():
            self.title.SetFont(wxFont(12,wxNORMAL,wxNORMAL,wxBOLD))
        else:
            self.title.SetFont(wxFont(wxDEFAULT,wxNORMAL,wxNORMAL,wxBOLD))

        # Set correct dimensions on current panel.
        if self.currentPanel.GetSizer():
            w,h = self.preferencesWindow.GetSizeTuple()
            self.currentPanel.GetSizer().SetDimension(0,0,w,h)
                   
    def GetPreferences(self):
        """
        Returns a preference object reflecting current state in dialog.

        ** Returns **
        
        *preferences* Preferences object

        """
        # Set all values available in panels.
        self.preferences.SetPreference(Preferences.LOG_TO_CMD,
                                       self.loggingPanel.GetLogToCmd())
        self.preferences.SetPreference(Preferences.STARTUP_MEDIA,
                                       self.nodePanel.GetMediaStartup())
        self.preferences.SetPreference(Preferences.ENABLE_DISPLAY,
                                       self.nodePanel.GetDisplay())
        self.preferences.SetPreference(Preferences.ENABLE_VIDEO,
                                       self.nodePanel.GetVideo())
        self.preferences.SetPreference(Preferences.ENABLE_AUDIO,
                                        self.nodePanel.GetAudio())
        self.preferences.SetPreference(Preferences.NODE_URL,
                                       self.nodePanel.GetDefaultNodeUrl())

        if self.nodePanel.GetDefaultNodeConfig():
            self.preferences.SetPreference(Preferences.NODE_CONFIG,
                                           self.nodePanel.GetDefaultNodeConfig().name)
            self.preferences.SetPreference(Preferences.NODE_CONFIG_TYPE,
                                           self.nodePanel.GetDefaultNodeConfig().type)
        self.preferences.SetPreference(Preferences.RECONNECT,
                                       self.venueConnectionPanel.GetReconnect())
        self.preferences.SetPreference(Preferences.MAX_RECONNECT,
                                       self.venueConnectionPanel.GetMaxReconnects())
        self.preferences.SetPreference(Preferences.RECONNECT_TIMEOUT,
                                       self.venueConnectionPanel.GetReconnectTimeOut())
        self.preferences.SetPreference(Preferences.MULTICAST,
                                       self.networkPanel.GetMulticast())
        self.preferences.SetPreference(Preferences.BEACON,
                                       self.networkPanel.GetBeacon())
        self.preferences.SetPreference(Preferences.DISPLAY_MODE,
                                       self.navigationPanel.GetDisplayMode())
        cDict = self.loggingPanel.GetLogCategories()
        for category in cDict.keys():
            self.preferences.SetPreference(category, cDict[category])

        p = self.profilePanel.GetNewProfile()
        self.preferences.SetProfile(p)

        return self.preferences
            
    def OnSelect(self, event):
        '''
        Called when selecting new preference from side menu. Each preference
        is associated with a panel, which is shown when the preference is selected.
        '''
        # Panel associated with the selected preference.
        item = event.GetItem()
        panel = self.sideTree.GetItemData(item).GetData()
        self.title.SetValue(self.sideTree.GetItemText(item))
        
        # Switch displayed panel.
        s = self.preferencesWindow.GetSizer()
        s.Remove(self.currentPanel)
        self.currentPanel.Hide()
        self.currentPanel = panel

        # Fix layout
        self.currentPanel.Show()
                       
        self.__Layout()
        
        w,h = self.preferencesWindow.GetSizeTuple()
        self.preferencesPanel.GetSizer().SetDimension(0,0,w,h)
                    
    def __InitTree(self):
        '''
        Populates the side tree and associates each preference with a panel.
        '''
        self.root = self.sideTree.AddRoot("")
        self.profile = self.sideTree.AppendItem(self.root,
                                                " My Profile")
        self.node = self.sideTree.AppendItem(self.root,
                                                " My Node")
        self.logging = self.sideTree.AppendItem(self.root,
                                                " Logging")
        self.venueConnection = self.sideTree.AppendItem(self.root,
                                                " Venue Connection")
        self.network = self.sideTree.AppendItem(self.root,
                                                " Network")
        self.navigation = self.sideTree.AppendItem(self.root,
                                                " Navigation")
        self.sideTree.SetItemData(self.profile,
                                  wxTreeItemData(self.profilePanel))
        self.sideTree.SetItemData(self.node,
                                  wxTreeItemData(self.nodePanel))
        self.sideTree.SetItemData(self.logging,
                                  wxTreeItemData(self.loggingPanel))
        self.sideTree.SetItemData(self.venueConnection,
                                  wxTreeItemData(self.venueConnectionPanel))
        self.sideTree.SetItemData(self.network,
                                  wxTreeItemData(self.networkPanel))
        self.sideTree.SetItemData(self.navigation,
                                  wxTreeItemData(self.navigationPanel))
        self.sideTree.SelectItem(self.profile)

    def __OnSize(self,event):
        '''
        Called when window is resized.
        '''
        self.__Layout()

    def __OnSashDrag(self, event):
        '''
        Called when sash panel is moved, resizes sash windows accordingly.
        '''
        if event.GetDragStatus() == wxSASH_STATUS_OUT_OF_RANGE:
            return
        
        eID = event.GetId()
        
        if eID == self.ID_WINDOW_LEFT:
            width = event.GetDragRect().width
            self.sideWindow.SetSize(wxSize(width, -1))
            
        elif eID == self.ID_WINDOW_RIGHT:
            width = event.GetDragRect().width
            self.preferencesWindow.SetSize(wxSize(width, -1))

        self.__Layout()
                                 
    def __Layout(self):
        '''
        Fix ui layout
        '''
        mainSizer = wxBoxSizer(wxVERTICAL)
        
        sizer = wxBoxSizer(wxHORIZONTAL)
        sizer.Add(self.sideWindow,0,wxEXPAND)
        sizer.Add(self.preferencesWindow,1,wxEXPAND)

        mainSizer.Add(sizer, 1, wxEXPAND)
        prefBox = wxBoxSizer(wxHORIZONTAL)
        self.preferencesWindow.SetSizer(prefBox)
       
        prefBox.Add(self.currentPanel, 1, wxEXPAND)

        prefPanelBox = wxBoxSizer(wxVERTICAL)
        self.preferencesPanel.SetSizer(prefPanelBox)
        prefPanelBox.Add(self.title, 0, wxEXPAND)
        prefPanelBox.Add(self.currentPanel, 1, wxEXPAND|wxTOP, 5)

        buttonSizer = wxBoxSizer(wxHORIZONTAL)
        buttonSizer.Add(self.okButton, 0, wxRIGHT | wxALIGN_CENTER, 5)
        buttonSizer.Add(self.cancelButton, 0, wxALIGN_CENTER)

        mainSizer.Add(buttonSizer, 0, wxALL| wxALIGN_CENTER, 5)

        w,h = self.preferencesWindow.GetSizeTuple()
        if self.currentPanel.GetSizer():
            self.currentPanel.GetSizer().SetDimension(0,0,w,h)

        self.SetSizer(mainSizer)
        self.Layout()

class NodePanel(wxPanel):
    def __init__(self, parent, id, preferences):
        wxPanel.__init__(self, parent, id)
        self.Centre()

        self.nodeText = wxStaticText(self, -1, "Node")
        self.nodeLine = wxStaticLine(self, -1)
        self.mediaButton = wxCheckBox(self, wxNewId(), "  Launch node services on startup ")
        self.nodeUrlText = wxStaticText(self, -1, "Node service URL")
        self.nodeUrlCtrl = wxTextCtrl(self, -1, "httptest", size = wxSize(250, -1))
        self.nodeConfigText = wxStaticText(self, -1, "Node configuration")
        self.mediaText = wxStaticText(self, -1, "Media")
        self.mediaLine = wxStaticLine(self, -1)
        self.audioButton = wxCheckBox(self, wxNewId(), " Enable Audio")
        self.displayButton = wxCheckBox(self, wxNewId(), " Enable Display")
        self.videoButton = wxCheckBox(self, wxNewId(), " Enable Video")

        if IsOSX():
            self.nodeText.SetFont(wxFont(12,wxNORMAL,wxNORMAL,wxBOLD))
            self.mediaText.SetFont(wxFont(12,wxNORMAL,wxNORMAL,wxBOLD))
        else:
            self.nodeText.SetFont(wxFont(wxDEFAULT,wxNORMAL,wxNORMAL,wxBOLD))
            self.mediaText.SetFont(wxFont(wxDEFAULT,wxNORMAL,wxNORMAL,wxBOLD))

        self.mediaButton.SetValue(int(preferences.GetPreference(Preferences.STARTUP_MEDIA)))
        self.nodeUrlCtrl.SetValue(preferences.GetPreference(Preferences.NODE_URL))
        self.audioButton.SetValue(int(preferences.GetPreference(Preferences.ENABLE_AUDIO)))
        self.displayButton.SetValue(int(preferences.GetPreference(Preferences.ENABLE_DISPLAY)))
        self.videoButton.SetValue(int(preferences.GetPreference(Preferences.ENABLE_VIDEO)))

        default = ""
        try:
            selections = map(lambda c:c.name + " ("+c.type+")", preferences.GetNodeConfigs())
            defaultNodeName = preferences.GetPreference(Preferences.NODE_CONFIG)
            defaultNodeType = preferences.GetPreference(Preferences.NODE_CONFIG_TYPE)
            
            self.configMap = {}
            
            for config in preferences.GetNodeConfigs():
                self.configMap[config.name + " ("+config.type +")"] = config

            log.debug("default node config: %s", default)
            log.debug("node configs: %s", str(selections))
        except:
            log.exception("Preferences:NodePanel: Failed to load node service configurations.")
            selections = ["No configurations, run node service"]
                    
        self.nodeConfigCtrl = wxComboBox(self, wxNewId(),
                                         defaultNodeName + " ("+defaultNodeType+")",
                                         choices = selections,
                                         style = wxCB_DROPDOWN,
                                         size = wxSize(235, -1))
        self.__Layout()

    def GetDefaultNodeUrl(self):
        return self.nodeUrlCtrl.GetValue()

    def GetDefaultNodeConfig(self):
        key = self.nodeConfigCtrl.GetValue()

        if key and self.configMap.has_key(key):
            return self.configMap[key]
        else:
            return None

    def GetMediaStartup(self):
        if self.mediaButton.IsChecked():
            return 1
        else:
            return 0

    def GetDisplay(self):
        if self.displayButton.GetValue():
            return 1
        else:
            return 0

    def GetVideo(self):
        if self.videoButton.GetValue():
            return 1
        else:
            return 0

    def GetAudio(self):
        if self.audioButton.GetValue():
            return 1
        else:
            return 0
    
    def __Layout(self):
        sizer = wxBoxSizer(wxVERTICAL)

        sizer2 = wxBoxSizer(wxHORIZONTAL)
        sizer2.Add(self.nodeText, 0, wxALL, 5)
        sizer2.Add(self.nodeLine, 1, wxALIGN_CENTER | wxALL, 5)
        sizer.Add(sizer2, 0, wxEXPAND)

        gridSizer = wxFlexGridSizer(0, 2, 5, 5)
        gridSizer.Add(self.nodeUrlText, 0, wxALL, 5)
        gridSizer.Add(self.nodeUrlCtrl)
        sizer.Add(gridSizer, 0, wxALL, 5)
                
        sizer.Add(self.mediaButton, 0, wxALL|wxEXPAND, 10)
        gridSizer = wxFlexGridSizer(0, 2, 5, 5)
        gridSizer.Add(self.nodeConfigText, 0, wxTOP | wxBOTTOM, 5)
        gridSizer.Add(self.nodeConfigCtrl)
        sizer.Add(gridSizer, 0, wxLEFT, 30)

        sizer2 = wxBoxSizer(wxHORIZONTAL)
        sizer2.Add(self.mediaText, 0, wxALL, 5)
        sizer2.Add(self.mediaLine, 1, wxALIGN_CENTER | wxALL, 5)
        sizer.Add(sizer2, 0, wxEXPAND)

        sizer.Add(self.audioButton, 0, wxEXPAND|wxALL, 10)
        sizer.Add(self.displayButton, 0, wxEXPAND|wxALL, 10)
        sizer.Add(self.videoButton, 0, wxEXPAND|wxALL, 10)
                                       
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.SetAutoLayout(1)
               
class ProfilePanel(wxPanel):
    def __init__(self, parent, id, preferences):
        wxPanel.__init__(self, parent, id)
        self.Centre()
        self.nameText = wxStaticText(self, -1, "Name:")
        self.nameCtrl = wxTextCtrl(self, -1, "", size = (400,-1),
                                   validator = TextValidator("Name"))
        self.emailText = wxStaticText(self, -1, "Email:")
        self.emailCtrl = wxTextCtrl(self, -1, "",
                                    validator = TextValidator("Email"))
        
        self.phoneNumberText = wxStaticText(self, -1, "Phone Number:")
        self.phoneNumberCtrl = wxTextCtrl(self, -1, "")
        self.locationText = wxStaticText(self, -1, "Location:")
        self.locationCtrl = wxTextCtrl(self, -1, "")
        self.homeVenue= wxStaticText(self, -1, "Home Venue:")
        self.homeVenueCtrl = wxTextCtrl(self, -1, "")
        self.profileTypeText = wxStaticText(self, -1, "Profile Type:")
       
        self.profile = None
        self.profileTypeBox = None
        self.dnText = None
        self.dnTextCtrl = None
       
        self.titleLine = wxStaticLine(self,-1)
        self.buttonLine = wxStaticLine(self,-1)
        self.__Layout()
        self.SetProfile(preferences.GetProfile())
        
    def __SetEditable(self, editable):
        if not editable:
            self.nameCtrl.SetEditable(false)
            self.emailCtrl.SetEditable(false)
            self.phoneNumberCtrl.SetEditable(false)
            self.locationCtrl.SetEditable(false)
            self.homeVenueCtrl.SetEditable(false)
            #self.profileTypeBox.SetEditable(false)
            self.dnTextCtrl.SetEditable(false)
        else:
            self.nameCtrl.SetEditable(true)
            self.emailCtrl.SetEditable(true)
            self.phoneNumberCtrl.SetEditable(true)
            self.locationCtrl.SetEditable(true)
            self.homeVenueCtrl.SetEditable(true)
            #self.profileTypeBox.SetEditable(true)
        log.debug("VenueClientUI.py: Set editable in successfully dialog")
           
    def __Layout(self):
        self.sizer1 = wxBoxSizer(wxVERTICAL)
        self.gridSizer = wxFlexGridSizer(0, 2, 5, 5)
        self.gridSizer.Add(self.nameText, 0, wxALIGN_LEFT, 0)
        self.gridSizer.Add(self.nameCtrl, 0, wxEXPAND, 0)
        self.gridSizer.Add(self.emailText, 0, wxALIGN_LEFT, 0)
        self.gridSizer.Add(self.emailCtrl, 0, wxEXPAND, 0)
        self.gridSizer.Add(self.phoneNumberText, 0, wxALIGN_LEFT, 0)
        self.gridSizer.Add(self.phoneNumberCtrl, 0, wxEXPAND, 0)
        self.gridSizer.Add(self.locationText, 0, wxALIGN_LEFT, 0)
        self.gridSizer.Add(self.locationCtrl, 0, wxEXPAND, 0)
        self.gridSizer.Add(self.homeVenue, 0, wxALIGN_LEFT, 0)
        self.gridSizer.Add(self.homeVenueCtrl, 0, wxEXPAND, 0)
        self.gridSizer.Add(self.profileTypeText, 0, wxALIGN_LEFT, 0)
        if self.profileTypeBox:
            self.gridSizer.Add(self.profileTypeBox, 0, wxEXPAND, 0)
        if self.dnText:
            self.gridSizer.Add(self.dnText, 0, wxALIGN_LEFT, 0)
            self.gridSizer.Add(self.dnTextCtrl, 0, wxEXPAND, 0)

        self.gridSizer.AddGrowableCol(1)
        self.sizer1.Add(self.gridSizer, 1, wxALL|wxEXPAND, 10)
        self.SetSizer(self.sizer1)
        self.sizer1.Fit(self)
        self.SetAutoLayout(1)
        self.Layout()
        
    def GetNewProfile(self):
        if(self.profile != None):
            self.profile.SetName(self.nameCtrl.GetValue())
            self.profile.SetEmail(self.emailCtrl.GetValue())
            self.profile.SetPhoneNumber(self.phoneNumberCtrl.GetValue())
            self.profile.SetLocation(self.locationCtrl.GetValue())
            self.profile.SetHomeVenue(self.homeVenueCtrl.GetValue())
            self.profile.SetProfileType(self.profileTypeBox.GetValue())

            if(self.profileTypeBox.GetSelection()==0):
                self.profile.SetProfileType('user')
            else:
                self.profile.SetProfileType('node')
                
        log.debug("ProfileDialog.GetNewProfile: Got profile information from dialog")
        return self.profile

    def Validate(self):
        self.nameCtrl.Validate()

    def SetProfile(self, profile):
        self.profile = profile
        self.profileTypeBox = wxComboBox(self, -1, choices =['user', 'node'], 
                                         style = wxCB_DROPDOWN|wxCB_READONLY)
        self.profileTypeBox.SetValue(self.profile.GetProfileType())
        self.__Layout()
        self.nameCtrl.SetValue(self.profile.GetName())
        self.emailCtrl.SetValue(self.profile.GetEmail())
        self.phoneNumberCtrl.SetValue(self.profile.GetPhoneNumber())
        self.locationCtrl.SetValue(self.profile.GetLocation())
        self.homeVenueCtrl.SetValue(self.profile.GetHomeVenue())
        if(self.profile.GetProfileType() == 'user'):
            self.profileTypeBox.SetSelection(0)
        else:
            self.profileTypeBox.SetSelection(1)
       
        self.__SetEditable(true)
        log.debug("ProfileDialog.SetProfile: Set profile information successfully in dialog")

class LoggingPanel(wxPanel):
    def __init__(self, parent, id, preferences):
        wxPanel.__init__(self, parent, id)
        self.Centre()
        self.preferences = preferences
        self.cmdButton = wxCheckBox(self, wxNewId(), "  Display log messages in command window ")
        self.locationText = wxStaticText(self, -1, "Location of log files")
        self.locationCtrl = wxTextCtrl(self, -1, AGTkConfig.instance().GetLogDir(),
                                       size = wxSize(30, -1),  style = wxTE_READONLY)
        self.levelText = wxStaticText(self, -1, "Log levels ")
        self.scWindow = wxScrolledWindow(self, -1, size = wxSize(10,50),
                                         style = wxSUNKEN_BORDER)
        self.scWindow.SetBackgroundColour("WHITE")
        self.scWindow.EnableScrolling(true, true)
        self.scWindow.SetScrollbars(20, 20, 10, 10)

        self.logWidgets = {}
        self.logs = Log.GetCategories()
        self.logLevels = Log.GetLogLevels()
        logInt = self.logLevels.keys()
        logInt.sort()
        self.logLevelsSorted = []
        
        for i in logInt:
            self.logLevelsSorted.append(self.logLevels[i])
            
        self.cmdButton.SetValue(int(preferences.GetPreference(Preferences.LOG_TO_CMD)))

        self.__Layout()

    def __GetLogInt(self, logString):
        for value in self.logLevels.keys():
            if self.logLevels[value] == logString:
                return value
        
    def GetLogToCmd(self):
        if self.cmdButton.IsChecked():
            return 1
        else:
            return 0

    def GetLogCategories(self):
        categories = {}
        for category in self.logWidgets.keys():
            stringLevel = self.logWidgets[category].GetValue()
            intLevel = self.__GetLogInt(stringLevel)
            categories[category] = intLevel

        return categories
        
    def __Layout(self):
        self.logWidgets.clear()
        
        sizer = wxBoxSizer(wxVERTICAL)
        sizer.Add(self.cmdButton, 0, wxALL|wxEXPAND, 10)
       
        gridSizer = wxFlexGridSizer(0, 2, 5, 5)
        gridSizer.Add(self.locationText, 0)
        gridSizer.Add(self.locationCtrl,0 , wxEXPAND)
        gridSizer.AddGrowableCol(1)
        sizer.Add(gridSizer, 0, wxEXPAND| wxALL, 10)
        sizer.Add(self.levelText, 0, wxLEFT, 10)

        gridSizer = wxFlexGridSizer(0, 2, 5, 5)
        gridSizer.Add(wxSize(5,5))
        gridSizer.Add(wxSize(5,5))
        for logName in self.logs:
            gridSizer.Add(wxStaticText(self.scWindow, -1, logName), 0, wxLEFT, 5)
            try:
                logLevel = int(self.preferences.GetPreference(logName))
            except:
                logLevel = Log.DEBUG
           
            combo = wxComboBox(self.scWindow, -1,
                               self.logLevels[logLevel], 
                               choices = self.logLevelsSorted,
                               style = wxCB_DROPDOWN)
            gridSizer.Add(combo, 0, wxEXPAND|wxRIGHT, 5)
            # Save widget so we can retreive value later.
            self.logWidgets[logName] = combo

        gridSizer.Add(wxSize(5,5))
        gridSizer.AddGrowableCol(1)
        self.scWindow.SetSizer(gridSizer)
        gridSizer.Fit(self.scWindow)
        self.scWindow.SetAutoLayout(1)
                
        sizer.Add(self.scWindow, 1, wxEXPAND| wxALL, 10)
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.SetAutoLayout(1)


class TextValidator(wxPyValidator):
    def __init__(self, fieldName):
        wxPyValidator.__init__(self)
        self.fieldName = fieldName
            
    def Clone(self):
        return TextValidator(self.fieldName)

    def Validate(self, win):
        tc = self.GetWindow()
        val = tc.GetValue()
        profile = win.GetNewProfile()

        if(len(val) < 1 or profile.IsDefault() 
             or profile.name == '<Insert Name Here>'
             or profile.email == '<Insert Email Address Here>'):
            
            if profile.name == '<Insert Name Here>':
                self.fieldName == 'Name'
            elif profile.email ==  '<Insert Email Address Here>':
                self.fieldName = 'Email'
                
            MessageDialog(NULL, "Please, fill in the %s field" %(self.fieldName,))
            return false
        return true

    def TransferToWindow(self):
        return true # Prevent wxDialog from complaining.

    def TransferFromWindow(self):
        return true # Prevent wxDialog from complaining.

class VenueConnectionPanel(wxPanel):
    def __init__(self, parent, id, preferences):
        wxPanel.__init__(self, parent, id)
        self.Centre()
        self.titleText = wxStaticText(self, -1, "Recovery")
        self.titleLine = wxStaticLine(self, -1)
        self.reconnectButton = wxCheckBox(self, wxNewId(), "  Allow automatic reconnection to venues ")
        self.maxText = wxStaticText(self, -1, "Recovery attempts ")
        self.maxReconnect = wx.lib.intctrl.IntCtrl(self, -1, 3, size = wxSize(30, -1))
        self.timeoutText = wxStaticText(self, -1, "Recovery timeout (seconds) ")
        self.timeout = wx.lib.intctrl.IntCtrl(self, -1, 10, size = wxSize(30, -1)) 
        reconnect = int(preferences.GetPreference(Preferences.RECONNECT))
        self.reconnectButton.SetValue(reconnect)
        self.maxReconnect.SetValue(int(preferences.GetPreference(Preferences.MAX_RECONNECT)))
        self.timeout.SetValue(int(preferences.GetPreference(Preferences.RECONNECT_TIMEOUT)))
        self.EnableCtrls(reconnect)
                
        if IsOSX():
            self.titleText.SetFont(wxFont(12,wxNORMAL,wxNORMAL,wxBOLD))
                                
        else:
            self.titleText.SetFont(wxFont(wxDEFAULT,wxNORMAL,wxNORMAL,wxBOLD))
                                
        self.__Layout()

        EVT_CHECKBOX(self, self.reconnectButton.GetId(), self.ReconnectCB)

    def GetReconnect(self):
        if self.reconnectButton.IsChecked():
            return 1
        else:
            return 0

    def GetMaxReconnects(self):
        return self.maxReconnect.GetValue()

    def GetReconnectTimeOut(self):
        return self.timeout.GetValue()

    def EnableCtrls(self, value):
        self.maxReconnect.Enable(value)
        self.timeout.Enable(value)

    def ReconnectCB(self, event):
        self.EnableCtrls(event.IsChecked())

    def __Layout(self):
        sizer = wxBoxSizer(wxVERTICAL)
        sizer2 = wxBoxSizer(wxHORIZONTAL)
        sizer2.Add(self.titleText, 0, wxALL, 5)#,0,wxEXPAND|wxALL,10)
        sizer2.Add(self.titleLine, 1, wxALIGN_CENTER | wxALL, 5)
        sizer.Add(sizer2, 0, wxEXPAND)
        sizer.Add(self.reconnectButton, 0, wxALL|wxEXPAND, 10)

        gridSizer = wxGridSizer(0, 2, 5, 5)
        gridSizer.Add(self.maxText, 0, wxLEFT, 30)
        gridSizer.Add(self.maxReconnect)
        gridSizer.Add(self.timeoutText, 0, wxLEFT, 30)
        gridSizer.Add(self.timeout)
        sizer.Add(gridSizer)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.SetAutoLayout(1)

class NetworkPanel(wxPanel):
    def __init__(self, parent, id, preferences):
        wxPanel.__init__(self, parent, id)
        self.Centre()
        self.titleText = wxStaticText(self, -1, "Multicast")
        self.titleLine = wxStaticLine(self, -1)
        self.multicastButton = wxCheckBox(self, wxNewId(), "  Use multicast ")
        
        self.multicastButton.SetValue(int(preferences.GetPreference(Preferences.MULTICAST)))

        self.beaconButton = wxCheckBox(self, wxNewId(), "  Run beacon ")
        
        self.beaconButton.SetValue(int(preferences.GetPreference(Preferences.BEACON)))
                        
                        
        if IsOSX():
            self.titleText.SetFont(wxFont(12,wxNORMAL,wxNORMAL,wxBOLD))
        else:
            self.titleText.SetFont(wxFont(wxDEFAULT,wxNORMAL,wxNORMAL,wxBOLD))
                                
        self.__Layout()
         
    def GetMulticast(self):
        if self.multicastButton.IsChecked():
            return 1
        else:
            return 0

    def GetBeacon(self):
        if self.beaconButton.IsChecked():
            return 1
        else:
            return 0
          
    def __Layout(self):
        sizer = wxBoxSizer(wxVERTICAL)
        sizer2 = wxBoxSizer(wxHORIZONTAL)
        sizer2.Add(self.titleText, 0, wxALL, 5)
        sizer2.Add(self.titleLine, 1, wxALIGN_CENTER | wxALL, 5)
        sizer.Add(sizer2, 0, wxEXPAND)
        sizer.Add(self.multicastButton, 0, wxALL|wxEXPAND, 10)
        sizer.Add(self.beaconButton, 0, wxALL|wxEXPAND, 10)
        
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.SetAutoLayout(1)

        
class NavigationPanel(wxPanel):
    def __init__(self, parent, id, preferences):
        wxPanel.__init__(self, parent, id)
        self.Centre()
        self.titleText = wxStaticText(self, -1, "Navigation View")
        self.titleLine = wxStaticLine(self, -1)
        self.exitsButton = wxRadioButton(self, wxNewId(), "  Show Exits ")
        self.myVenuesButton = wxRadioButton(self, wxNewId(), "  Show My Venues ")
        self.allVenuesButton = wxRadioButton(self, wxNewId(), "  Show All Venues ")

        value = preferences.GetPreference(Preferences.DISPLAY_MODE)
        if value == Preferences.EXITS:
            self.exitsButton.SetValue(1)
        elif value == Preferences.MY_VENUES:
            self.myVenuesButton.SetValue(1)
        elif value == Preferences.ALL_VENUES:
            self.allVenuesButton.SetValue(1)
               
        if IsOSX():
            self.titleText.SetFont(wxFont(12,wxNORMAL,wxNORMAL,wxBOLD))
        else:
            self.titleText.SetFont(wxFont(wxDEFAULT,wxNORMAL,wxNORMAL,wxBOLD))
                                
        self.__Layout()
         
    def GetDisplayMode(self):
        if self.exitsButton.GetValue():
            return Preferences.EXITS
        elif self.myVenuesButton.GetValue():
            return Preferences.MY_VENUES
        elif self.allVenuesButton.GetValue():
            return Preferences.ALL_VENUES
          
    def __Layout(self):
        sizer = wxBoxSizer(wxVERTICAL)
        sizer2 = wxBoxSizer(wxHORIZONTAL)
        sizer2.Add(self.titleText, 0, wxALL, 5)
        sizer2.Add(self.titleLine, 1, wxALIGN_CENTER | wxALL, 5)
        sizer.Add(sizer2, 0, wxEXPAND)
        sizer.Add(self.exitsButton, 0, wxALL|wxEXPAND, 10)
        sizer.Add(self.myVenuesButton, 0, wxALL|wxEXPAND, 10)
        sizer.Add(self.allVenuesButton, 0, wxALL|wxEXPAND, 10)
               
        self.SetSizer(sizer)
        sizer.Fit(self)
        self.SetAutoLayout(1)
        
if __name__ == "__main__":
    from AccessGrid.Toolkit import WXGUIApplication
    
    pp = wxPySimpleApp()

    # Init the toolkit with the standard environment.
    app = WXGUIApplication()

    # Try to initialize
    app.Initialize("Preferences")
    
    p = Preferences()
    pDialog = PreferencesDialog(NULL, -1,
                                'Preferences', p)
    pDialog.ShowModal()
    p = pDialog.GetPreferences()
    p.StorePreferences()
