#-----------------------------------------------------------------------------
# Name:        SharedPresentation.py
# Purpose:     This is the Shared Presentation Software. 
#
# Author:      Ivan R. Judson, Tom Uram
#
# Created:     2002/12/12
# RCS-ID:      $Id: SharedPresentation.py,v 1.47 2007-01-24 21:28:19 wwjag Exp $
# Copyright:   (c) 2003
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------

# Normal import stuff
import os
import sys
import getopt
from threading import Thread
import Queue
import shutil

from wxPython.wx import *
from AccessGrid import Platform
from AccessGrid import Log

try:
    from twisted.internet import threadedselectreactor
    threadedselectreactor.install()
except:
    pass

from twisted.internet import reactor


if sys.platform == Platform.WIN:
    # Win 32 COM interfaces that we use
    try:
        import win32com
        import win32com.client
    except:
        print "No Windows COM support!"
        sys.exit(1)
elif sys.platform == Platform.OSX:
    from MacPPTViewer import MacPPTViewer
else:
    # An OpenOffice/StarOffice Viewer
    # We will add options to make the viewer selectable if we have
    #   a choice of more than one viewer.
    from ImpressViewer import ImpressViewer

# Imports we need from the Access Grid Module
from AccessGrid import Platform
from AccessGrid.Toolkit import WXGUIApplication
#from AccessGrid import DataStore
from AccessGrid.SharedAppClient import SharedAppClient
from AccessGrid.DataStoreClient import GetVenueDataStore
from AccessGrid.interfaces.Venue_client import VenueIW
from AccessGrid.Platform.Config import UserConfig
from AccessGrid.ClientProfile import ClientProfile
from AccessGrid.UIUtilities import MessageDialog
from AccessGrid import icons

class ViewerSoftwareNotInstalled(Exception):
    pass

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Viewer code
#
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class PowerPointViewer:
    """
    The PowerPoint Viewer is meant to be a single instance of a Presentation
    viewer. On platforms other than windows or mac, where MS Office isn't
    available there might be a different viewer for the data.

    The specifics for the PowerPoint Viewer are related to using the
    win32com interface for controlling PowerPoint from within
    python. What we do is set self.ppt to a python COM interface of an
    instance of the powerpoint application. From there it's using
    internal COM interfaces to do various operations on the PowerPoint
    Application to make it do what we want.

    Here's a description of what we're keeping track of and why:

    self.ppt -- win32com Interface to an instance of the PowerPoint Application
    self.presentation -- The current presentation.
    self.win -- The window showing a slideshow of the current presentation.
    """

    def __init__(self, log):
        """
        We aren't doing anything in here because we really don't need
        anything yet. Once things get started up externally, this gets fired
        up through the other methods.
        """
        self.log = log
        self.ppt = None
        self.presentation = None
        self.win = None

        self.pptAlreadyOpen = 0
        # The filename of the currently open file.
        self.openFile = ""

        from win32com.client import gencache
        import pythoncom
        pythoncom.CoInitialize()
     
       
        try:
            gencache.EnsureModule('{91493440-5A91-11CF-8700-00AA0060263B}', 0, 2, 6)
        except IOError:
            self.log.exception("Failed to ensure module, try to create a local copy")
            # This may be caused if a non-admin user runs the shared
            # presentation for the first time without write access to
            # Python\site-packages\win32com\gen_py. Try to create the
            # module in the local directory instead and import it.

            from win32com.client import makepy
            
            localModule = open("PowerPointModule.py", 'w')
            
            makepy.GenerateFromTypeLibSpec("Microsoft PowerPoint 10.0 Object Library", localModule)
            
            if localModule:
                localModule.close()

            import PowerPointModule
        
        except Exception, e:
            self.log.exception("Failed to ensure module")
            raise ViewerSoftwareNotInstalled()
    
    def Start(self):
        """
        This method actually fires up PowerPoint and if specified opens a
        file and starts viewing it.
        """
        # Instantiate the powerpoint application via COM
        self.ppt = win32com.client.Dispatch("PowerPoint.Application")

        if self.ppt.Presentations.Count > 0:
            self.pptAlreadyOpen = 1

        # Make it active (visible)
        self.ppt.Activate()

    def Stop(self):
        """
        This method shuts the powerpoint application down.
        """
        # Turn the slide show off
        self.EndShow()
       

    def Quit(self):
        """
        This method quits the powerpoint application.
        """
        # Close the presentation
        try:
            if self.presentation:
                self.presentation.Close()
        except:
            print 'can not close presentation....continue anyway'
            self.log.exception('can not close presentation....continue anyway')
                
        # Exit the powerpoint application, but only if 
        # it was opened by the viewer
        if not self.pptAlreadyOpen:
            self.ppt.Quit()
        
    def LoadPresentation(self, file):
        """
        This method opens a file and starts the viewing of it.
        """

        print '---------- load presentation'
        # Close existing presentation
        try:
            if self.presentation:
                self.presentation.Close()
        except:
            print 'can not close previous presentation...continue anyway'
            self.log.exception('can not close presentation....continue anyway')
        # Open a new presentation and keep a reference to it in self.presentation
        
        file.replace("%20", " ")
        self.presentation = self.ppt.Presentations.Open(file)
        self.lastSlide = self.presentation.Slides.Count
        print '================== set open file to ', file
        self.openFile = file
        
        # Start viewing the slides in a window
        self.presentation.SlideShowSettings.ShowType = win32com.client.constants.ppShowTypeWindow
        self.win = self.presentation.SlideShowSettings.Run()
       
    def Next(self):
        """
        This method moves to the next slide.
        """
        # Move to the next slide
        self.win.View.Next()

    def Previous(self):
        """
        This method moves to the previous slide.
        """
        # Move to the previous slide
        self.win.View.Previous()

    def GoToSlide(self, slide):
        """
        This method moves to the specified slide.
        """
        # Move to the specified Slide
        self.win.View.GotoSlide(int(slide))

    def EndShow(self):
        """
        This method quits the viewing of the current set of slides.
        """
        # Quit the presentation
      
        if self.win:
            self.win.View.Exit()
            self.win = None

    def GetLastSlide(self):
        """
        This method returns the index of the last slide (indexed from 1)
        """
        return self.lastSlide

    def GetSlideNum(self):
        """
        This method returns the index of the current slide
        """
        return self.win.View.CurrentShowPosition

    def GetStepNum(self):
        """
        This method returns the step of the current slide
        """
        return self.win.View.Slide.PrintSteps



# Depending on the platform decide which viewer to use
if sys.platform == Platform.WIN:
    # If we're on Windows we try to use the python/COM interface to PowerPoint
    defaultViewer = PowerPointViewer
elif sys.platform == Platform.LINUX or sys.platform == Platform.FREEBSD5 or sys.platform == Platform.FREEBSD6:
    # On Linux the best choice is probably Open/Star Office
    defaultViewer = ImpressViewer
elif sys.platform == Platform.OSX:
    # If we 're on Mac OSX, we try to use the AppleScript interface to PowerPoint
    defaultViewer = MacPPTViewer
else:
    defaultViewer = None



#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# GUI code
#
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class SharedPresentationFrame(wxFrame):

    ID_SYNC = wxNewId()
    ID_LOCALUPLOAD = wxNewId()
    ID_CLEAR = wxNewId()
    ID_EXIT = wxNewId()
    ID_HELP_INST = wxNewId()

    def __init__(self, parent, ID, title, log=None):
        wxFrame.__init__(self, parent, ID, title,
                         wxDefaultPosition)

        self.log = log
        
        # Initialize callbacks
        noOp = lambda x=0:0
        self.loadCallback = noOp
        #self.clearSlidesCallback = noOp
        self.prevCallback = noOp
        self.nextCallback = noOp
        self.gotoCallback = noOp
        self.masterCallback = noOp
        self.closeCallback = noOp
        self.syncCallback = noOp
        self.exitCallback = noOp
        self.localUploadCallback = noOp
        reactor.interleave(wxCallAfter)
        #
        # Create UI controls
        #
                
        # - Create menu bar
        menubar = wxMenuBar()
        fileMenu = wxMenu()
        self.fileMenu = fileMenu
        fileMenu.Append(self.ID_SYNC,"&Sync", "Sync to app state")
        fileMenu.Append(self.ID_LOCALUPLOAD,"&Upload Local File", "Upload local file to venue.")
        fileMenu.Append(self.ID_CLEAR,"&Clear slides", "Clear the slides from venue")
        fileMenu.AppendSeparator()
        fileMenu.Append(self.ID_EXIT,"&Exit", "Exit")
     	menubar.Append(fileMenu, "&File")

        self.helpMenu = wxMenu()
        self.helpMenu.Append(self.ID_HELP_INST, "&Instructions", "Instructions on how to use the shared presentation viewer.")
        menubar.Append(self.helpMenu, "&Help")
        self.SetMenuBar(menubar)

        self.SetIcon(icons.getAGIconIcon())
      
        # - Create main panel
        self.panel = wxPanel(self, -1, size = wxSize(320, 140))
        # - Create main sizer 
        mainSizer = wxBoxSizer(wxVERTICAL)
        self.SetSizer(mainSizer)
    
        mainSizer.Add(self.panel, 1, wxEXPAND)
        
        # - Create panel sizer
        sizer = wxBoxSizer(wxVERTICAL)
        self.panel.SetSizer(sizer)
                    
        # - Create checkbox for master
        self.masterCheckBox = wxCheckBox(self.panel,-1,"Take control as presentation master")
        sizer.Add((5, 5))
        sizer.Add( self.masterCheckBox, 0, wxEXPAND | wxALL, 5)

        # - Create sizer for remaining ctrls
        staticBoxSizer = wxBoxSizer(wxVERTICAL)
        gridSizer = wxFlexGridSizer(2, 3, 5, 5)
        gridSizer.AddGrowableCol(1)
        staticBoxSizer.Add(gridSizer, 0, wxEXPAND)
        sizer.Add(staticBoxSizer, 0, wxEXPAND| wxALL, 5)

        # - Create textctrl for slide url
        staticText = wxStaticText(self.panel, -1, "Slides")
        #self.slidesText = wxTextCtrl(self,-1)
        self.slidesCombo = wxComboBox(self.panel ,wxNewId(), style=wxCB_DROPDOWN|wxCB_SORT)
        self.slidesCombo.Append("")
        self.loadButton = wxButton(self.panel ,-1,"Load", wxDefaultPosition, wxSize(40,21) )

        gridSizer.Add( staticText, 0, wxALIGN_LEFT)
        gridSizer.Add( self.slidesCombo, 1, wxEXPAND | wxALIGN_LEFT)
        gridSizer.Add( self.loadButton, 2, wxALIGN_RIGHT)

        # Don't update the filelist until user becomes a master (it won't 
        #   be needed unless user is a master).
        # self.updateVenueFileList()

        # - Create textctrl for slide num
        staticText = wxStaticText(self.panel, -1, "Slide number")
        self.slideNumText = wxTextCtrl(self.panel ,-1, size = wxSize(40, 20))
        self.goButton = wxButton(self.panel ,-1,"Go", wxDefaultPosition, wxSize(40,21))
        gridSizer.Add( staticText, wxALIGN_LEFT)
        gridSizer.Add( self.slideNumText )
        gridSizer.Add( self.goButton, wxALIGN_RIGHT )

        # - Create buttons for control 
        rowSizer = wxBoxSizer(wxHORIZONTAL)
        self.prevButton = wxButton(self.panel ,-1,"<Prev")
        self.nextButton = wxButton(self.panel ,-1,"Next>")
        rowSizer.Add( self.prevButton , 0, wxRIGHT, 5)
        rowSizer.Add( self.nextButton )

        sizer.Add(rowSizer, 0, wxALIGN_CENTER|wxALL, 5)
        sizer.Add((5,5))
        
        self.SetAutoLayout(1)
        self.Layout()

        # Initially, I'm not the master
        self.SetMaster(0)
               
        # Set up event callbacks
        EVT_TEXT_ENTER(self, self.slidesCombo.GetId(), self.OpenCB)
        EVT_CHECKBOX(self, self.masterCheckBox.GetId(), self.MasterCB)
        EVT_SET_FOCUS(self.slidesCombo, self.ComboCB)
        EVT_BUTTON(self, self.prevButton.GetId(), self.PrevSlideCB)
        EVT_TEXT_ENTER(self, self.slideNumText.GetId(), self.GotoSlideNumCB)
        EVT_BUTTON(self, self.nextButton.GetId(), self.NextSlideCB)
        EVT_BUTTON(self, self.loadButton.GetId(), self.OpenCB)
        EVT_BUTTON(self, self.goButton.GetId(), self.GotoSlideNumCB)

        EVT_MENU(self, self.ID_SYNC, self.SyncCB)
        EVT_MENU(self, self.ID_LOCALUPLOAD, self.LocalUploadCB)
        EVT_MENU(self, self.ID_CLEAR, self.ClearSlidesCB)
        EVT_MENU(self, self.ID_EXIT, self.ExitCB)
        EVT_MENU(self, self.ID_HELP_INST, self.OpenInstructionsCB)


    #~~~~~~~~~~~~~~~~~~~~~~~~~~
    #
    # Callback stubs for the UI
    #
    def ComboCB(self, event):
        """
        Callback for clicking on combobox for slides
        """
        try:
            # Load list of presentation slides from venue to combobox
            self.updateVenueFileList()

            # Skip event to preserve normal behaviour of the combobox 
            event.Skip()
        except:
            self.log.exception("ComboCB")
            MessageDialog(self, "An error occurred when clicking on the combo box.", "Combo Box Error")

    def PrevSlideCB(self,event):
        """
        Callback for "previous" button
        """
        try:
            self.prevCallback()
        except:
            self.log.exception("PrevSlideCB")
            MessageDialog(self, "An error occurred going to the previous slide.", "Previous Slide Error")

    def NextSlideCB(self,event):
        """
        Callback for "next" button
        """
        try:
            self.nextCallback()
        except:
            self.log.exception("NextSlideCB")
            MessageDialog(self, "An error occurred going to the next slide.", "Next Slide Error")

    def GotoSlideNumCB(self,event):
        """
        Callback for "enter" presses in the slide number text field
        """
        try:
            if self.masterCheckBox.IsChecked():
                slideNum = int(self.slideNumText.GetValue())
                self.gotoCallback(slideNum)
        except:
            self.log.exception("GotoSlideNumCB")
            MessageDialog(self, "An error occurred going to a slide number.", "Goto Slide Number Error")

    def MasterCB(self,event):
        """
        Callback for "master" checkbox
        """
        try:
            flag = self.masterCheckBox.IsChecked()
            self.masterCallback(flag)
        except:
            self.log.exception("MasterCB")
            MessageDialog(self, "An error occurred when toggling the master checkbox.", "Master Checkbox Error")

    def OpenCB(self,event):
        """
        Callback for "enter" presses in the slide URL text field
        """
    
        try:
            if self.masterCheckBox.IsChecked():
                # Get slide url from text field
                slidesUrl = self.slidesCombo.GetValue()
                slidesUrl = slidesUrl.replace("%20", " ")
                                
                # Call the load callback
                try:
                    self.loadCallback(slidesUrl)
                except:
                    self.log.exception('SharedPresentation.OpenCB: Can not load presentation %s'%(slidesUrl))
                    wxCallAfter(self.ShowMessage,"Can not load presentation %s"%slidesUrl, "Notification")
        except:
            self.log.exception("OpenCB")
            MessageDialog(self, "An error occurred when opening a url.", "Open Error")

    def SyncCB(self,event):
        """
        Callback for "sync" menu item
        """
        try:
            self.syncCallback()
        except:
            self.log.exception("SyncCB")
            MessageDialog(self, "An error occurred when syncing.", "Sync Error")

    def LocalUploadCB(self,event):
        """
        Callback for "LocalUpload" menu item
        """
        try:
            dlg = wxFileDialog(self, "Choose a file to upload:", style = wxOPEN | wxMULTIPLE)

            if dlg.ShowModal() == wxID_OK:
                files = dlg.GetPaths()
                self.log.debug("SharedPresentation.LocalUploadCB:%s " %str(files))

                # To display an individual error message, upload each file separately. 
                for file in files:
                    try:
                        self.localUploadCallback([file])
                    except:
                        self.log.exception("Can not upload file %s to data store"%file)
                        wxCallAfter(self.ShowMessage, "Can not upload presentation %s"%file, "Notification")
                    
                self.updateVenueFileList()
        except:
            self.log.exception("LocalUploadCB")
            MessageDialog(self, "An error occurred when attempting a local upload.", "Local Upload Error")

    def ClearSlidesCB(self,event):
        """
        Callback for "clear slides" menu item
        """
        try:
            self.closeCallback()
        except:
            self.log.exception("ClearSlidesCB")
            MessageDialog(self, "An error occurred when clearing slides.", "Clear Slides Error")

    def ExitCB(self,event):
        """
        Callback for 'Exit' menu item
        """
        try:
            self.exitCallback()
        except:
            self.log.exception("ExitCB")

    def OpenInstructionsCB(self, event):
        """
        Callback for 'Instructions' help menu item
        """
        try:
            info =  "If you want to be the leader of this session, select the master check box below.\nAll presentation files located in the data area of this venue are now available here.\nChoose a file from these available slides or enter the URL address of your presentation.\nClick the Load button to open the presentation. \n\nNote: Please, only use this controller window to change slides."
        
            MessageDialog(self, info, "Instructions")
        except:
            self.log.exception("ClearSlidesCB")
            MessageDialog(self, "An error occurred showing the application's intructions.", "Intructions Error")
        
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #
    # Client methods
    #

    def SetCallbacks(self, loadCallback, 
                           prevCallback, 
                           nextCallback, 
                           gotoCallback,
                           masterCallback,
                           closeCallback,
                           syncCallback,
                           exitCallback,
                           localUploadCallback,
                           queryVenueFilesCallback):
        """
        This method is used to set callbacks for the UI
        """
        self.loadCallback = loadCallback
        self.prevCallback = prevCallback
        self.nextCallback = nextCallback
        self.gotoCallback = gotoCallback
        self.masterCallback = masterCallback
        self.closeCallback = closeCallback
        #self.clearSlidesCallback = closeCallback
        self.syncCallback = syncCallback
        self.exitCallback = exitCallback
        self.localUploadCallback = localUploadCallback
        self.queryVenueFilesCallback = queryVenueFilesCallback

    def SetSlideNum(self, slideNum):
        """
        This method is used to set the slide number
        """
        self.slideNumText.SetValue('%s' % slideNum)

    def SetSlides(self, slides):
        """
        This method is used to set the slide URL
        """
        self.slidesCombo.SetValue(slides)

    def ShowMessage(self, message, title):
        """
        This method is used to display a message dialog to the user.
        """
        MessageDialog(self, message, title, style = wxOK|wxICON_INFORMATION)
  
    def SetMaster(self, flag):
        """
        This method is used to set the "master" checkbox
        """
        self.masterCheckBox.SetValue(flag)

        self.slideNumText.SetEditable(flag)
        self.prevButton.Enable(flag)
        self.nextButton.Enable(flag)
        self.loadButton.Enable(flag)
        self.goButton.Enable(flag)
        self.slidesCombo.Enable(flag)
        # If we're becoming the master, make sure our list of files is current.
        if flag:
            self.updateVenueFileList()

    def updateVenueFileList(self):
        """
        This method is used to update the list of files from the venue.
        """
        old_value = self.slidesCombo.GetValue()
        # Fill slides combo box with venue's files.
        
        try:
            if sys.platform == Platform.WIN:
                filenames = self.queryVenueFilesCallback("*.ppt")
            else:
                filenames = self.queryVenueFilesCallback(["*.ppt", "*.sxi"])
            self.slidesCombo.Clear()
            for file in filenames:
                self.slidesCombo.Append(file)
        except:
            self.log.exception("Exception getting filenames from venue.")
        # Restore value that was unset when we updated the list.
        self.slidesCombo.SetValue(old_value)


class UIController(wxApp):

    def __init__(self,arg, log=None):
        self.log = log
        wxApp.__init__(self,arg)

    def OnInit(self):
        self.frame = SharedPresentationFrame(NULL, -1, "Shared Presentation Controller", log=self.log)
        self.frame.Fit()
        self.frame.Show(true)
        self.SetTopWindow(self.frame)
        return true

    def Start(self):
        """
        Start the UI controller app loop
        """
        self.MainLoop()

    def SetCallbacks(self, loadCallback, 
                           prevCallback, 
                           nextCallback, 
                           gotoCallback,
                           masterCallback,
                           closeCallback,
                           syncCallback,
                           exitCallback,
                           localUploadCallback,
                           queryVenueFilesCallback):
        """
        Pass-through to frame's SetCallbacks method
        """

        self.frame.SetCallbacks(loadCallback, 
                                prevCallback, 
                                nextCallback, 
                                gotoCallback,
                                masterCallback,
                                closeCallback,
                                syncCallback,
                                exitCallback,
                                localUploadCallback,
                                queryVenueFilesCallback)

    def SetMaster(self,flag):
        """
        Pass-through to frame's SetMaster method
        """
        self.frame.SetMaster(flag)

    def SetSlides(self,slidesUrl):
        """
        Pass-through to frame's SetSlides method
        """
        self.frame.SetSlides(slidesUrl)

    def ShowMessage(self, message, title):
        """
        Pass-through to frame's ShowMessage method
        """
        self.frame.ShowMessage(message, title)
      
    def SetSlideNum(self,slideNum):
        """
        Pass-through to frame's SetSlideNum method
        """
        self.frame.SetSlideNum(slideNum)

    

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Shared presentation constants classes
#
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class SharedPresEvent:
    NEXT = "next"
    PREV = "prev"
    MASTER = "master"
    GOTO = "goto"
    LOAD = "load"

    LOCAL_NEXT = "local next"
    LOCAL_PREV = "local prev"
    LOCAL_GOTO = "local goto"
    LOCAL_LOAD = "local load"
    LOCAL_LOAD_VENUE = "local load venue"
    LOCAL_CLOSE = "local close"
    LOCAL_SYNC = "local sync"
    LOCAL_QUIT = "local quit"
    LOCAL_NO_VIEWER = "local no viewer"

class SharedPresKey:
    SLIDEURL = "slideurl"
    SLIDENUM = "slidenum"
    STEPNUM = "stepnum"
    MASTER = "master"


#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Shared Presentation class itself
#
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class SharedPresentation:
    """
    The SharedPresentation is an Access Grid 2 Application. It is
    designed as an example that shows how reasonably complex
    applications can be built and shared through the AG2 toolkit.

    The SharedPresentation contains a Presentation Viewer and a
    Presentation Controller. These are designed to be generic so that
    they can be switched out with other implementations as necessary.
    """
    appName = "Shared Presentation"
    appDescription = "A shared presentation is a set of slides that someone presents to share an idea, plan, or activity with a group."
    appMimetype = "application/x-ag-shared-presentation"
    
    def __init__(self, url, venueUrl=None, appName = 'SharedPresentation', connectionId=None):
        """
        This is the contructor for the Shared Presentation.
        """
        
        
        # Create shared application client. 
        self.sharedAppClient = SharedAppClient(appName)
        self.log = self.sharedAppClient.InitLogging()

        self.controller = UIController(0, self.log)

        # Necessary for UI applications that sends event messages
        reactor.interleave(wxCallAfter)
        
        # Initialize state in the shared presentation
        self.url = url
        self.venueUrl = venueUrl
        self.connectionId = connectionId
       
        self.eventQueue = Queue.Queue(5)
        self.running = 0
        self.masterId = None
        self.numSteps = 0
        self.slideNum = 1

        # Set up method dictionary for the queue processor to call
        # callbacks based on the event type
        #
        # This is an ugly hack, so we can lookup methods by event type
        self.methodDict = dict()
        self.methodDict[SharedPresEvent.NEXT] = self.Next
        self.methodDict[SharedPresEvent.PREV] = self.Previous
        self.methodDict[SharedPresEvent.GOTO] = self.GoToSlide
        self.methodDict[SharedPresEvent.LOAD] = self.LoadPresentation
        self.methodDict[SharedPresEvent.MASTER] = self.SetMaster

        self.methodDict[SharedPresEvent.LOCAL_NEXT] = self.LocalNext
        self.methodDict[SharedPresEvent.LOCAL_PREV] = self.LocalPrev
        self.methodDict[SharedPresEvent.LOCAL_GOTO] = self.LocalGoto
        self.methodDict[SharedPresEvent.LOCAL_LOAD] = self.LocalLoad
        self.methodDict[SharedPresEvent.LOCAL_LOAD_VENUE] = self.LocalLoadVenue
        self.methodDict[SharedPresEvent.LOCAL_CLOSE] = self.ClosePresentation
        self.methodDict[SharedPresEvent.LOCAL_SYNC] = self.Sync
        self.methodDict[SharedPresEvent.LOCAL_QUIT] = self.Quit
        self.methodDict[SharedPresEvent.LOCAL_NO_VIEWER] = self.NoViewer

        # Get client profile
        try:
            clientProfileFile = os.path.join(UserConfig.instance().GetConfigDir(), "profile")
            clientProfile = ClientProfile(clientProfileFile)
        except:
            self.log.info("Could not load client profile, set clientProfile = None")
            clientProfile = None

        # Connect to shared application service. 
        self.sharedAppClient.Join(self.url, clientProfile)

        # Set venue url.
        if not self.venueUrl:
            self.venueUrl = self.sharedAppClient.GetVenueURL()
               

        # Register callbacks with the Data Channel to handle incoming
        # events.
        self.log.debug("Registering for events.")
        self.sharedAppClient.RegisterEventCallback(SharedPresEvent.NEXT, self.RecvNext)
        self.sharedAppClient.RegisterEventCallback(SharedPresEvent.PREV, self.RecvPrev)
        self.sharedAppClient.RegisterEventCallback(SharedPresEvent.GOTO, self.RecvGoto)
        self.sharedAppClient.RegisterEventCallback(SharedPresEvent.LOAD, self.RecvLoad)
        self.sharedAppClient.RegisterEventCallback(SharedPresEvent.MASTER, self.RecvMaster)

        # Create the controller
        self.log.debug("Creating controller.")
        
        self.controller.SetCallbacks( self.SendLoad,
                                      self.SendPrev,
                                      self.SendNext,
                                      self.SendGoto,
                                      self.SendMaster,
                                      self.ClearSlides,
                                      self.Sync,
                                      self.QuitCB,
                                      self.LocalUpload,
                                      self.QueryVenueFiles )
        
        # Start the queue thread
        Thread(target=self.ProcessEventQueue).start()

        # Start the controller 
        # (this is the main thread, so we'll block here until
        # the controller is closed)
        #self.controller.Start()

    def Start(self):
        self.controller.Start()
        # Put a quit event, so the viewer gets shut down correctly
        self.eventQueue.put([SharedPresEvent.LOCAL_QUIT, None])

        # When the quit event gets processed, the running flag gets cleared
        self.log.debug("Shutting down...")
        import time
        while self.running:
            print ".",
            time.sleep(1)
       
        # Shutdown sharedAppClient
        self.sharedAppClient.Shutdown()
       
    def OpenVenueData(self,venueDataUrl):
        """
        OpenFile opens the specified file in the viewer.
        Since the caller of this method loads the slide set,
        he is implicitly the master.
        """

        # Load the specified file
        self.eventQueue.put([SharedPresEvent.LOCAL_LOAD,venueDataUrl])


    def LoadFromVenue(self):
        """
        LoadFromVenue loads the presentation from the venue and
        moves to the current slide and step
        """
        self.eventQueue.put([SharedPresEvent.LOCAL_LOAD_VENUE,None])


    def ProcessEventQueue(self):
        # The queue processing thread is the only one allowed to access
        # the viewer; that keeps the requirements on the viewer minimal.
        # This method loops, processing events that it gets from the 
        # eventQueue.

        try:
            self.viewer = defaultViewer(self.log)
            self.viewer.Start()
           
        except ViewerSoftwareNotInstalled:
            self.log.debug("The necessary viewer software (for example power point) is not installed; exiting")
            self.eventQueue.put([SharedPresEvent.LOCAL_NO_VIEWER, None])
               
        # Loop, processing events from the event queue
        self.running = 1
        while self.running:

            # Pull the next event out of the queue
            (event, data) = self.eventQueue.get(1)
            self.log.debug("Got Event: %s %s"%(event, str(data)))

            # Invoke the matching method, passing the data
            try:
                self.methodDict[event](data)
            except:
                self.log.exception("EXCEPTION PROCESSING EVENT %s"%data)
                
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #
    # Methods registered as callbacks with the UI
    # These methods typically put an event in the event queue.
    #

    def SendNext(self):
        """
        This method handles NEXT button presses in the UI.
        The event is only sent if the local user is the "master"
        """
        self.log.debug("Method SendNext called")

        if self.masterId == self.sharedAppClient.GetPublicId():
            # Put the event on the queue
            self.eventQueue.put([SharedPresEvent.LOCAL_NEXT,None])


    def SendPrev(self):
        """
        This method handles PREV button presses in the UI.
        The event is only sent if the local user is the 'master'
        """
        self.log.debug("Method SendPrev called")

        if self.masterId == self.sharedAppClient.GetPublicId():
            # Put the event on the queue
            self.eventQueue.put([SharedPresEvent.LOCAL_PREV,None])


    def SendGoto(self, slideNum):
        """
        This method handles GOTO events from the UI.
        The event is only sent if the local user is the "master"
        """
        self.log.debug("Method SendGoto called; slidenum=(%d)"%slideNum)

        # Check if slideNum is greater than max slide
        if not self.viewer or not self.viewer.win:
            self.controller.ShowMessage("No slides are loaded.", "Notification")
            return
        
        lastPage = self.viewer.GetLastSlide()
        if slideNum > lastPage:
            self.controller.ShowMessage("Slide number is incorrect. Last slide is %s"%lastPage, "Notification")
            return

        if slideNum < 1:
            self.controller.ShowMessage("Slide number should be greater than 0.", "Notification")
            return
                   
        if self.masterId == self.sharedAppClient.GetPublicId():
            # Put the event on the queue
            self.eventQueue.put([SharedPresEvent.LOCAL_GOTO,slideNum])
       
    def SendLoad(self, path):
        """
        This method handles LOAD events from the UI.
        The event is only sent if the local user is the 'master'
        """
        path = path.replace("%20", " ")
        self.log.debug("Method SendLoad called; path=(%s)", path)

        if self.masterId == self.sharedAppClient.GetPublicId():
            self.eventQueue.put([SharedPresEvent.LOCAL_LOAD,path])

    def SendMaster(self, flag):
        """
        This method handles clicks on the MASTER checkbox
        """
        self.log.debug("Method SendMaster called; flag=(%d)"%flag)
        publicId = self.sharedAppClient.GetPublicId()

        if flag:
            # Local user wants to become master
            # Set the master in the venue
            self.log.debug("Sending master event with id %s", publicId)
            self.sharedAppClient.SetData(SharedPresKey.MASTER, publicId)
            # Send event
            self.sharedAppClient.SendEvent(SharedPresEvent.MASTER, publicId)
            
            try:
                self.sharedAppClient.SetParticipantStatus("master")
            except:
                self.log.exception("SharedPresentation:__init__: Failed to set participant status, old server?")
           
        else:
            # Local user has chosen to stop being master
            if self.masterId == publicId:
                self.log.debug(" Set master to empty")

                # Let's set the master in the venue
                self.sharedAppClient.SetData(SharedPresKey.MASTER, "no master")

                # Send event
                self.sharedAppClient.SendEvent(SharedPresEvent.MASTER, "no master")

                try:
                    self.sharedAppClient.SetParticipantStatus("connected")
                except:
                    self.log.exception("SharedPresentation:__init__: Failed to set participant status, old server?")
                    
               
            else:
                self.log.debug(" User is not master; skipping")


    def ClearSlides(self):
        """
        This method will clear the slides from the venue app object;
        and close the local presentation
        """
        self.log.debug("Method ClearSlides called")

        # Clear the slides url stored in the venue
        self.sharedAppClient.SetData(SharedPresKey.SLIDEURL, "")
        self.sharedAppClient.SetData(SharedPresKey.SLIDENUM, "")
        self.sharedAppClient.SetData(SharedPresKey.STEPNUM, "")

        self.eventQueue.put([SharedPresEvent.LOCAL_CLOSE, None])

    def Sync(self):
        """
        This method will sync the viewer with the state in the app object
        """
        self.log.debug("Method Sync called")

        # Also, update the list of venue ppt files in the dropdown menu.
        # This method does not exist in this class.
        #self.updateVenueFileList()

        self.eventQueue.put([SharedPresEvent.LOCAL_LOAD_VENUE,None])

    def QuitCB(self):
        """
        This method puts a "quit" event in the queue, to get the
        viewer to shutdown
        """
        self.log.debug("Method QuitCB called")
        self.eventQueue.put([SharedPresEvent.LOCAL_QUIT, None])


    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #
    # Methods registered as callbacks with EventClient
    # These methods typically put an event in the event queue.
    #

    def RecvNext(self, event):
        """
        This callback puts the "next" event from the network on
        the event queue.
        """
        self.log.debug("Method RecvNext called")

        if self.masterId == self.sharedAppClient.GetPublicId():
            self.log.debug("got my own event; skip")
            return

        if self.masterId == event.GetSenderId():
            # We put the passed in event on the event queue
            try:
                self.eventQueue.put([SharedPresEvent.NEXT, (event.GetSenderId(), event.GetData()) ])
            except Queue.Full:
                self.log.debug("Dropping event, event Queue full!")

    def RecvPrev(self, event):
        """
        This callback puts the "previous" event from the network on
        the event queue.
        """
        self.log.debug("Method RecvPrev called")

        if self.masterId == self.sharedAppClient.GetPublicId():
            self.log.debug( "got my own event; skip")
            return

        if self.masterId == event.GetSenderId():
            # We put the passed in event on the event queue
            try:
                self.eventQueue.put([SharedPresEvent.PREV, (event.GetSenderId(), event.GetData()) ])
            except Queue.Full:
                self.log.debug("Dropping event, event Queue full!")
        
    def RecvGoto(self, event):
        """
        This callback puts the "goto" event from the network on
        the event queue.
        """
        self.log.debug("Method RecvGoto called")

        if self.masterId == self.sharedAppClient.GetPublicId():
            self.log.debug( "got my own event; skip")
            return

        if self.masterId == event.GetSenderId():
            # We put the passed in event on the event queue
            try:
                self.eventQueue.put([SharedPresEvent.GOTO, event.GetData()])
            except Full:
                self.log.debug("Dropping event, event Queue full!")
        
    def RecvLoad(self, event):
        """
        This callback puts the "load" presentation event from
        the network on the event queue.
        """
        self.log.debug("Method RecvLoad called")
      
        if self.masterId == self.sharedAppClient.GetPublicId():
            self.log.debug( "got my own event; skip")
            return

        if self.masterId == event.GetSenderId():
            # We put the passed in event on the event queue
            try:
                self.eventQueue.put([SharedPresEvent.LOAD, (event.GetSenderId(), event.GetData()) ])
            except Full:
                self.log.debug("Dropping event, event Queue full!")

            
    def RecvMaster(self, event):
        """
        This callback puts a "master" event from the network
        on the event queue
        """
        self.log.debug("Method RecvMaster called")

        # We put the passed in event on the event queue
        try:
            self.eventQueue.put([SharedPresEvent.MASTER, (event.GetSenderId(), event.GetData()) ])
        except Full:
            self.log.debug("Dropping event, event Queue full!")

    

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #
    # Methods called by the queue processor for incoming events.
    # These methods can communicate with the viewer, since they
    # are called by the queue processing thread, in which the
    # viewer was created.
    #   

    def Next(self, data=None):
        """
        This is the _real_ next slide method that tells the viewer to move
        to the next slide.
        """
        self.log.debug("Method Next called")

        # Call the viewers Next method
        if self.viewer != None:
            self.viewer.Next()
            wxCallAfter(self.controller.SetSlideNum,self.viewer.GetSlideNum())
        else:
            wxCallAfter(self.controller.ShowMessage, "No slides are loaded.", "Notification")
            self.log.debug("No presentation loaded")
        
    def Previous(self, data=None):
        """
        This is the _real_ previous slide method that tells the viewer to move
        to the previous slide.
        """
        self.log.debug("Method Previous called")

        # Call the viewers Previous method
        if self.viewer != None:
            self.viewer.Previous()
            wxCallAfter(self.controller.SetSlideNum,self.viewer.GetSlideNum())
        else:
            wxCallAfter(self.controller.ShowMessage, "No slides are loaded.", "Notification")
            self.log.debug("No presentation loaded!")

    def GoToSlide(self, slideNum):
        """
        This is the _real_ goto slide method that tells the viewer to move
        to the specified slide.
        """
        self.log.debug("Method GoToSlide called; slidenum=(%d)"%int(slideNum))

        # Call the viewers GotoSlide method
        if self.viewer != None:
            self.viewer.GoToSlide(slideNum)
        else:
            wxCallAfter(self.controller.ShowMessage, "No slides are loaded.", "Notification")
            self.log.debug("No presentation loaded!")

        wxCallAfter(self.controller.SetSlideNum, slideNum)
                   
    def LoadPresentation(self, data):
        """
        This is the _real_ load presentation method that tells the viewer
        to load the specified presentation.
        data is a tuple of (senderId, url)
        """
        self.log.debug("Method LoadPresentation called; url=(%s)"%data[1])

        slidesUrl = data[1]
        slidesUrl = slidesUrl.replace("%20", " ")
        # If the slides URL does not begin with http, assume
        # the slides reside in the venue data store
        if not slidesUrl.startswith('http'):
            ##
            ## FIXME:
            ## Should use the real name of the file, and download it to 
            ## a 'Received Files' directory instead of temp so user can
            ## find it in the future
            ##
            tmpFile = os.path.join(UserConfig.instance().GetTempDir(), "presentation.ppt")
            # Make sure filename is not currently open
            if tmpFile == self.viewer.openFile:
                tmpFile = os.path.join(UserConfig.instance().GetTempDir(), "presentation2.ppt")
           
            try:
                ds = GetVenueDataStore(self.venueUrl, self.connectionId)
                # Since we assume ftps means a datastore url, we ignore much
                # of it. We could verify the file url matches the datastore.
                ds.Download(slidesUrl, tmpFile)
                self.viewer.LoadPresentation(tmpFile)
            except:
                self.log.exception("Can not load presentation %s"%slidesUrl)
                wxCallAfter(self.controller.ShowMessage,
                            "Can not load presentation %s." %slidesUrl, "Notification")
               
        else:
            try:
                self.viewer.LoadPresentation(slidesUrl)
            except:
                self.log.exception("Can not load presentation %s" %slidesUrl)
                wxCallAfter(self.controller.ShowMessage,
                            "Can not load presentation %s." %slidesUrl, "Notification")
              
        if slidesUrl[:6] == "ftps:":
            # Remove datastore prefix on local url in UI since master checks
            #  if file is in venue and sends full datastore url if it is.
            short_filename = self.stripDatastorePrefix(slidesUrl)
            wxCallAfter(self.controller.SetSlides, short_filename)
            #self.controller.SetSlides(slidesUrl)
        else:
            wxCallAfter(self.controller.SetSlides, slidesUrl)
            
        wxCallAfter(self.controller.SetSlideNum, 1)
        self.slideNum = 1
        self.stepNum = 0
        
    def stripDatastorePrefix(self, url):
        vproxy = VenueIW(self.venueUrl)
        ds = vproxy.GetDataStoreInformation()
        ds_prefix = str(ds[0])
        url_beginning = url[:len(ds_prefix)]
        # If it starts with the prefix ds[1], return just the ending.
        if ds_prefix == url_beginning and ds_prefix[:6] == "ftps:":
            # Get url without datastore ds_prefix, +1 is for extra "/" 
            short_url = url[len(ds_prefix)+1:]
            #print "url stripped to:", short_url
            return short_url
        else:
            # Does not start with datastore prefix, leave it alone.
            return url

    def SetMaster(self, data):
        """
        This method sets the master of the presentation.
        data is a tuple of (senderId, masterid) 
        """
        self.log.debug("Method SetMaster called")

        # If I was master, change status in application service.
        if self.masterId == self.sharedAppClient.GetPublicId():
            try:
                self.sharedAppClient.SetParticipantStatus("connected")
            except:
                self.log.exception("SharedPresentation:__init__: Failed to set participant status, old server?")

        # Store the master's public id locally
        self.log.debug("Setting master id to %s", data[1])
        self.masterId = data[1]

        # Update the controller accordingly
        if self.masterId == self.sharedAppClient.GetPublicId():
            wxCallAfter(self.controller.SetMaster, true)
        else:
            wxCallAfter(self.controller.SetMaster, false)

    def ClosePresentation(self,data=None):
        """
        This method closes the presentation in the viewer
        """

        self.log.debug("Method ClosePresentation called")
        try:
            self.viewer.EndShow()
        except:
            self.log.exception("Can not end show, ignore")

    def NoViewer(self, data=None):
        wxCallAfter(self.controller.ShowMessage, "The necessary viewer software (for example PowerPoint) is not installed", "Viewer Not Installed")
        self.Quit()
        
    def Quit(self, data=None):
        """
        This is the _real_ Quit method that tells the viewer to quit
        """
        self.log.debug("Method Quit called")
        
        # Stop the viewer
        try:
            self.viewer.Stop()
        except:
            self.log.exception("Exception stopping show")

        # Close the viewer
        try:
            self.viewer.Quit()
        except:
            self.log.exception("Exception quitting viewer")

        # Destroy controller
        try:
            self.controller.frame.Destroy()
        except wxPyDeadObjectError:
            self.log.info("Exception destroying controller. This happens when using the x button in the top right corner. Not critical.")
        except:
            self.log.exception("Exception destroy controller.")
        
        # Get rid of the controller
        self.controller = None
        
        # Turn off the main loop
        self.running = 0


    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #
    # Methods called by the queue processor for local events.
    # These methods can communicate with the viewer, since they
    # are called by the queue processing thread, in which the
    # viewer was created.
    # 

    def LocalNext(self, data):
        """
        This is the _real_ next slide method that tells the viewer to move
        to the next slide.
        """
        self.log.debug("Method LocalNext called")

        if self.viewer != None and self.viewer.win != None:
            # Careful not to slip off the end of the presentation, cause that mean an exception
            if self.slideNum == self.viewer.GetLastSlide() and self.stepNum >= self.viewer.GetStepNum()-1:
                wxCallAfter(self.controller.ShowMessage,
                            "This is the last slide. You can not go to next.", "Notification")
                return

            if self.slideNum <= self.viewer.GetLastSlide():
                
                # Call the viewers Next method
                self.viewer.Next()

                # Get the slide number from the viewer
                slideNum = self.viewer.GetSlideNum()
                if slideNum != self.slideNum:

                    # Set the slide number in the controller
                    wxCallAfter(self.controller.SetSlideNum, slideNum)

                    # Store the slide number in the app object
                    self.sharedAppClient.SetData(SharedPresKey.SLIDENUM, slideNum)
                    self.slideNum = slideNum
                    self.stepNum = 0
                else:
                    # The presentation advanced, but the slide number didn't change,
                    # so it musta been an on-slide transition or some such
                    self.stepNum += 1

                # Store the step number in the app object
                self.sharedAppClient.SetData(SharedPresKey.STEPNUM, self.stepNum)

                # Send the next event to other app users
                self.sharedAppClient.SendEvent(SharedPresEvent.NEXT, "")
        else:
            wxCallAfter(self.controller.ShowMessage, "No slides are loaded.", "Notification")
            self.log.debug("No presentation loaded!")
        
    def LocalPrev(self, data):
        """
        This is the _real_ previous slide method that tells the viewer to move
        to the next slide.
        """
        self.log.debug("Method LocalPrev called")
       
        if self.viewer != None and self.viewer.win != None:
            if self.slideNum < 2:
                wxCallAfter(self.controller.ShowMessage,
                            "This is the first slide. You can not go to previous.", "Notification")
                
            if self.slideNum > 0:

                # Call the viewers Previous method
                self.viewer.Previous()
                                    
                # Get the slide number from the viewer
                slideNum = self.viewer.GetSlideNum()
                if slideNum != self.slideNum:
                    # Set the slide number in the controller
                    wxCallAfter(self.controller.SetSlideNum, slideNum)

                    self.slideNum = slideNum
                    self.stepNum = self.viewer.GetStepNum() - 1

                    # Store the slide number in the app object
                    self.sharedAppClient.SetData(SharedPresKey.SLIDENUM, slideNum)

                else:
                    # The presentation retreated, but the slide number didn't change,
                    # so it musta been an on-slide transition or some such
                    if self.stepNum > 0: 
                        self.stepNum -= 1

                # Store the step number in the app object
                self.sharedAppClient.SetData(SharedPresKey.STEPNUM, self.stepNum)

                # We send the event, which is wrapped in an Event instance
                self.sharedAppClient.SendEvent(SharedPresEvent.PREV, "")

                self.log.debug("slide %d step %d"%(self.slideNum, self.stepNum))

        else:
            wxCallAfter(self.controller.ShowMessage, "No slides are loaded.", "Notification")
            self.log.debug("No presentation loaded!")

        
    def LocalGoto(self, slideNum):
        """
        This is the _real_ goto slide method that tells the viewer to goto
        the specified slide.
        """
        self.log.debug("Method LocalGoto called; slidenum=(%d)"%slideNum)
        # Call the viewers GotoSlide method
        if self.viewer != None and self.viewer.win != None:
            if slideNum > 0 and slideNum <= self.viewer.GetLastSlide():
                self.viewer.GoToSlide(slideNum)
                self.sharedAppClient.SetData(SharedPresKey.SLIDENUM, slideNum)
                self.slideNum = slideNum
                self.stepNum = 0
                self.sharedAppClient.SetData(SharedPresKey.STEPNUM, self.stepNum)

                # Send event
                self.sharedAppClient.SendEvent(SharedPresEvent.GOTO, self.slideNum)
                
        else:
            wxCallAfter(self.controller.ShowMessage, "No slides are loaded.", "Notification")
            self.log.debug("No presentation loaded!")

        wxCallAfter(self.controller.SetSlideNum, slideNum)
    
    def LocalLoad(self, slidesUrl):
        """
        This is the _real_ goto slide method that tells the viewer to move
        to the next slide.
        """
        self.log.debug("Method LocalLoad called; slidesUrl=(%s)"%slidesUrl)
        slidesUrl = slidesUrl.replace("%20", " ")
        # If the slides URL does not begin with 'http', assume the
        # slides reside in the venue data store
        if not slidesUrl.startswith('http:'):
            tmpFile = os.path.join(UserConfig.instance().GetTempDir(), "presentation.ppt")
            # If current filename is in use, use slightly different name.
            if tmpFile == self.viewer.openFile:
                tmpFile = os.path.join(UserConfig.instance().GetTempDir(), "presentation2.ppt")
           
            try:
                ds = GetVenueDataStore(self.venueUrl, self.connectionId)
                # Since we assume ftps means a datastore url, we ignore much
                # of it. We could verify the file url matches the datastore.
                filename = slidesUrl.split('/')[-1]
                ds.Download(filename, tmpFile)
                self.viewer.LoadPresentation(tmpFile)
               
            except:
                self.log.exception("Can not load presentation %s"%slidesUrl)
                wxCallAfter(self.controller.ShowMessage,
                            "Can not load presentation %s." %slidesUrl,
                            "Notification")
               
            # Remove datastore prefix on local url in UI since master checks
            #  if file is in venue and sends full datastore url if it is.
            short_url = self.stripDatastorePrefix(slidesUrl)
            wxCallAfter(self.controller.SetSlides, short_url)
            #self.controller.SetSlides(slidesUrl)
        else:
            try:
                self.viewer.LoadPresentation(slidesUrl)
            except:
                self.log.exception("Can not load presentation %s"%slidesUrl)
                wxCallAfter(self.controller.ShowMessage,
                            "Can not load presentation %s." %slidesUrl,
                            "Notification")
               
                
            wxCallAfter(self.controller.SetSlides, slidesUrl)

        self.slideNum = 1
        self.stepNum = 0
        wxCallAfter(self.controller.SetSlideNum, self.slideNum)

        self.sharedAppClient.SetData(SharedPresKey.SLIDEURL, slidesUrl)
        self.sharedAppClient.SetData(SharedPresKey.SLIDENUM, self.slideNum)
        self.sharedAppClient.SetData(SharedPresKey.STEPNUM, self.stepNum)
        
        # Send event
        self.sharedAppClient.SendEvent(SharedPresEvent.LOAD, slidesUrl)
                                    
        self.SendMaster(true)


    def LocalLoadVenue(self, data=None):
        """
        This is the _real_ goto slide method that tells the viewer to move
        to the next slide.
        """
        self.log.debug("Method LocalLoadVenue called")

        # Retrieve the current presentation
        self.presentation = self.sharedAppClient.GetData(SharedPresKey.SLIDEURL)
        errorFlag = false
        # Check i presentation still exists.

        # Set the slide URL in the UI
        if self.presentation and len(self.presentation) != 0:
            self.presentation.replace("%20", " ")
            self.log.debug("Got presentation: %s"%self.presentation)
            wxCallAfter( self.controller.SetSlides, self.presentation)
                                
            # Retrieve the current slide
            self.slideNum = int(self.sharedAppClient.GetData(SharedPresKey.SLIDENUM))
            # If it's a string, convert it to an integer
            if type(self.slideNum) == type(""):
                if len(self.slideNum) < 1:
                    self.slideNum = 1
                else:
                    self.slideNum = int(self.slideNum)

            # Retrieve the current step number
            self.stepNum = int(self.sharedAppClient.GetData(SharedPresKey.STEPNUM))
            # If it's a string, convert it to an integer
            if type(self.stepNum) == type(""):
                if len(self.stepNum) < 1:
                    self.stepNum = 0
                else:
                    self.stepNum = int(self.stepNum)

            # Retrieve the master
            self.masterId = self.sharedAppClient.GetData(SharedPresKey.MASTER)

            # If the slides URL does not begin with 'http', assume the slides
            # reside in the venue data store
            if not self.presentation.startswith("http:"):
                tmpFile = os.path.join(UserConfig.instance().GetTempDir(), "presentation.ppt")
                # If tmpFile name is in use, use a different name.
                if tmpFile == self.viewer.openFile:
                    tmpFile = os.path.join(UserConfig.instance().GetTempDir(), "presentation2.ppt")
                try:
                    ds = GetVenueDataStore(self.venueUrl, self.connectionId)
                    # Since we assume ftps means a datastore url, we ignore much
                    # of it. We could verify the file url matches the datastore.
                    filename = self.presentation.split('/')[-1]
                    ds.Download(filename, tmpFile)
                    self.viewer.LoadPresentation(tmpFile)
                except:
                    errorFlag = 1
                    self.log.exception("Can not load file %s 5"%self.presentation)
                                                       
            else:
                try:
                    self.viewer.LoadPresentation(self.presentation)
                except:
                    errorFlag = 1
                    self.log.exception("Can not load file %s 6"%self.presentation)

            if not errorFlag:       
                # Go to the current slide
                self.GoToSlide(self.slideNum)

                # Go to the current step
                for i in range(self.stepNum):
                    self.Next()

            else:
                self.log.error("SharedPresentation.LocalLoadVenue: Can not load presentation %s"%(self.presentation))
                wxCallAfter(self.controller.ShowMessage,
                            "Can not load presentation %s." %self.presentation, "Notification")
                self.slideNum = ''
                
        # Set the slide number in the UI
        if self.slideNum == '':
            self.slideNum = 1
        else:
            self.log.debug("Got slide num: %d"%self.slideNum)
            wxCallAfter(self.controller.SetSlideNum, '%s' % self.slideNum)

        # Set the master in the UI
        wxCallAfter(self.controller.SetMaster, false)

    def LocalUpload(self, filenames):
        dsc = GetVenueDataStore(self.venueUrl, self.connectionId)
        for filename in filenames:
            dsc.Upload(filename)
            
    def QueryVenueFiles(self, file_query="*"):
        dsc = GetVenueDataStore(self.venueUrl, self.connectionId)
        if type(file_query) == type(""):
            filenames = dsc.QueryMatchingFiles(file_query)
        elif type(file_query) == type([]):
            filenames = dsc.QueryMatchingFilesMultiple(file_query)
        else:
            raise "InvalidQueryType"
        return filenames



#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Utility functions
#
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#
# This gets logging started given the log name passed in
# For more information about the logging module, check out:
# http://www.red-dove.com/python_logging.html
#

def Usage():
    """
    Standard usage information for users.
    """
    print "%s:" % sys.argv[0]
    print "    -a|--venueURL : <url to venue>"
    print "    -a|--applicationURL : <url to application in venue>"
    print "    -c|--connectionId : <VenueClient's connectionId>"
    print "    -d|--data : <url to data in venue>"
    print "    -h|--help : print usage"
    print "    -i|--information : <print information about this application>"
    print "    --debug : print debugging output"



#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# MAIN block
#
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

if __name__ == "__main__":
    
    # Initialization of variables
    venueURL = None
    appURL = None
    venueDataUrl = None
    connectionId = None
    name = "SharedPresentation"
    debug = 0

    app = WXGUIApplication()
    init_args = []
    if "--debug" in sys.argv or "-d" in sys.argv:
        init_args.append("--debug")
       
    app.Initialize(name,args=init_args)
    
    wxInitAllImageHandlers()

    # Here we parse command line options

    try:
        opts, args = getopt.getopt(sys.argv[1:], "d:v:a:l:c:ih",
                                   ["venueURL=", "applicationURL=",
                                    "information=", "connectionId=",
                                    "data=", "debug", "help"])
    except getopt.GetoptError:
        Usage()
        sys.exit(2)

    for o, a in opts:
        if o in ("-v", "--venueURL"):
            venueURL = a
        elif o in ("-a", "--applicationURL"):
            appURL = a
        elif o in ("-c", "--connectionId"):
            connectionId = a
        elif o in ("-i", "--information"):
            print "App Name: %s" % SharedPresentation.appName
            print "App Description: %s" % SharedPresentation.appDescription
            print "App Mimetype: %s" % SharedPresentation.appMimetype
            sys.exit(0)
        elif o in ("-d", "--data"):
            venueDataUrl = a
        elif o in ("--debug",):
            debug = 1
        elif o in ("-h", "--help"):
            Usage()
            sys.exit(0)
    
    # If we're not passed some url that we can use, bail showing usage
    if appURL == None and venueURL == None:
        Usage()
        sys.exit(0)

    # If we got a venueURL and not an applicationURL
    # This is only in the example code. When Applications are integrated
    # with the Venue Client, the application will only be started with
    # some applicatoin URL (it will never know about the Venue URL)
    if appURL == None and venueURL != None:
        venueProxy = Client.SecureHandle(venueURL).get_proxy()
        appURL = venueProxy.CreateApplication(SharedPresentation.appName,
                                              SharedPresentation.appDescription,
                                              SharedPresentation.appMimetype)
        log.debug("Application URL: %s", appURL)

   
    # This is all that really matters!
    presentation = SharedPresentation(appURL, venueURL, name, connectionId=connectionId)

    if venueDataUrl:
        presentation.OpenVenueData(venueDataUrl)
    else:
        presentation.LoadFromVenue()

    presentation.Start()

    # This is needed because COM shutdown isn't clean yet.
    # This should be something like:
    #sys.exit(0)
    os._exit(0)

