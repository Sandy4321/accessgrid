#-----------------------------------------------------------------------------
# Name:        SharedQuestionTool.py
# Purpose:     Tool for asking and answering questions.
#
# Author:      Susanne Lefvert
#
# Created:     $Date: 2007-09-18 20:45:33 $
# RCS-ID:      $Id: SharedQuestionTool.py,v 1.9 2007-09-18 20:45:33 turam Exp $
# Copyright:   (c) 2002
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------

import os
import sys

import logging
import sys
import getopt
from time import localtime, strftime
import xml.dom.minidom

import wx

from ObserverPattern import Observer, Model

from AccessGrid.SharedAppClient import SharedAppClient
from AccessGrid.Platform.Config import UserConfig
from AccessGrid.ClientProfile import ClientProfile
from AccessGrid import icons
from AccessGrid.GUID import GUID
from AccessGrid.Toolkit import WXGUIApplication
from AccessGrid.Platform import IsOSX 


class SharedQuestionTool(Model):
    """
    The SharedQuestionTool allows audience members to send questions to the
    moderator/presenter of a session.
    """
    
    SEND_QUESTION = "SendQuestion"
    REMOVE_QUESTION = "RemoveQuestion"
    
    def __init__( self, appUrl, name):
        '''
        Creates the shared application client, used for application service
        interaction, and opens the audience/moderatorView for UI display.
        '''
        Model.__init__(self)
        self.allQuestions = []

        # Create shared application client
        self.sharedAppClient = SharedAppClient(name)
        self.log = self.sharedAppClient.InitLogging()
        self.log.debug("SharedQuestionTool.__init__:Started shared question tool appUrl %s"
                       %(appUrl))
       
        # Get client profile
        try:
            clientProfileFile = os.path.join(UserConfig.instance().GetConfigDir(), "profile")
            self.clientProfile = ClientProfile(clientProfileFile)
        except:
            self.log.info("SharedQuestionTool.__init__: Could not load client profile, set clientProfile = None")
            self.clientProfile = None
    
        # Join the application session
        self.sharedAppClient.Join(appUrl, self.clientProfile)
        self.publicId = self.sharedAppClient.GetPublicId()

        # Register event callback
        self.sharedAppClient.RegisterEventCallback(self.SEND_QUESTION, self.SendQuestionCb)
        self.sharedAppClient.RegisterEventCallback(self.REMOVE_QUESTION, self.RemoveQuestionCb)

        # Get all questions currently stored in the application service
        clients = self.sharedAppClient.GetDataKeys()
        
        if clients:
            for clientId in clients:
                try:
                    list = self.sharedAppClient.GetData(clientId)
                    if len(list) > 0:
                        qlist = self.__FromXML(list)
                        for question in qlist:
                            self.allQuestions.append(question)
                except:
                    self.log.exception("SharedQuestionTool.__init__: Failed to get questions")
                
    def Shutdown(self):
        ''' Exit the application service.'''
        self.sharedAppClient.Shutdown()
        os._exit(1)
        
    #
    # Local GUI callbacks.
    #
    def SendQuestion(self, text):
        '''Called when an audience member clicks the send button.'''
        question = self.__CreateQuestion(text)
               
        myQuestions = self.GetMyQuestions()
        myQuestions.append(question)
              
        # Store question queue in the venue application service.
        self.sharedAppClient.SetData(self.publicId, self.__ToXML(myQuestions))

        # Send the event.
        self.sharedAppClient.SendEvent(self.SEND_QUESTION, question)

        return question
        
    def RemoveQuestion(self, question):
        '''Called when an audience member decides to cancel a question.'''
        myQuestions = self.GetMyQuestions()
        i = 0
        for q in myQuestions:
            if q["id"] == question["id"]:
                del myQuestions[i]
            i = i + 1
                          
        # Store question queue in the venue application service.
        self.sharedAppClient.SetData(self.publicId, self.__toXML(myQuestions))
                
        # Send the event.
        self.sharedAppClient.SendEvent(self.REMOVE_QUESTION, question)

    def GetAllQuestions(self, clientId = None):
        '''Returns the entire question list.'''
        return self.allQuestions

    def GetMyQuestions(self):
        '''Returns my question list.'''
        myQuestions = []
        for question in self.allQuestions:
            if question["appId"] == self.publicId:
                myQuestions.append(question)
            
        return myQuestions
                            
    #
    # Callbacks triggered by application service events.
    # 
    def SendQuestionCb(self, event):
        """ Callback invoked when incoming SEND_QUESTION events arrive."""
        question = event.GetData()
        self.allQuestions.append(question)

        self.NotifyObservers()
        
    def RemoveQuestionCb(self, event):
        """ Callback invoked when incoming SEND_REMOVE events arrive."""
        question = dict(event.GetData())

        i = 0
        for q in self.allQuestions:
            if question["id"] == q["id"]:
                del self.allQuestions[i]
            i = i + 1

        self.NotifyObservers()
    
    def __CreateQuestion(self, text):
        """
        Create a question dictionary.
        """
        question = dict()
        question["text"] = text
        question["timeStamp"] = strftime("%a, %d %b %Y, %H:%M:%S", localtime())
        question["id"] = str(GUID())
        question["clientProfile"] = self.clientProfile.name
        question["appId"] = str(self.publicId)

        return question

    def __ToXML(self, questionList):
        """
        Convert a list of question dictionaries to xml.
        """
        domImpl = xml.dom.minidom.getDOMImplementation()
        doc = domImpl.createDocument(xml.dom.minidom.EMPTY_NAMESPACE,
                                     "Data", '')
        qlistXML = doc.documentElement

        for q in questionList:
            qx = doc.createElement("Question")
            qx.setAttribute('text', q["text"])
            qx.setAttribute('timeStamp', q["timeStamp"])
            qx.setAttribute('id', q["id"])
            qx.setAttribute('clientProfile', q["clientProfile"])
            qx.setAttribute('appId', q["appId"])
            qlistXML.appendChild(qx)
                
        return doc.toxml()

    def __FromXML(self, questionListXML):
        """
        Convert an xml document to a list of question dictionaries.
        """
        questions = []
        domP = xml.dom.minidom.parseString(questionListXML)
        questionElements = domP.getElementsByTagName("Question")

        for q in questionElements:
            question = dict()
            question["text"] = q.attributes["text"].value
            question["timeStamp"] = q.attributes["timeStamp"].value
            question["id"] = q.attributes["id"].value
            question["clientProfile"] = q.attributes["clientProfile"].value
            question["appId"] = q.attributes["appId"].value
            questions.append(question)

        return questions
         
    
class SharedQuestionToolUI(wx.App):
    '''
    User interface to shared question tool including a moderator
    and participant view.
    '''

    def OnInit(self):
        return 1

    def OnExit(self):
        '''
        Invoked when closing the main window.
        '''
        self.questionTool.Shutdown()
        os._exit(1)

    def __init__( self, questionTool, log = None):
        '''
        Create ui components and register as observers to the
        shared question tool model.
        '''
        wx.App.__init__(self, False)
        self.log = log
        self.questionTool = questionTool
        self.mainSizer = None
        self.frame = wx.Frame(None, -1, "Shared Question Tool",
                             size = wx.Size(500, 500))
        self.frame.SetIcon(icons.getAGIconIcon())
        self.SetTopWindow(self.frame)
        self.topPanel = wx.Notebook(self.frame, -1)



        self.audienceView = AudienceView(self.topPanel, self.questionTool, 
					 self)
        self.moderatorView = ModeratorView(self.topPanel, self.questionTool, 
					   self)
	
	self.topPanel.AddPage(self.audienceView, "Audience View")


	self.topPanel.AddPage(self.moderatorView, "Moderator View")
       
        # Register observers
        self.questionTool.RegisterObserver(self.audienceView)
        self.questionTool.RegisterObserver(self.moderatorView)

        self.frame.Show(1)

    def Close(self):
	self.frame.Destroy()
    
class ModeratorView(wx.Panel, Observer):
    '''
    View for the moderator showing all sent and received questions.
    '''
    def __init__(self, parent, questionTool, app):
        '''
        Create ui components.
        '''
        wx.Panel.__init__(self, parent, -1)
        Observer.__init__(self)
        self.questionTool = questionTool
        self.parent = parent
        self.app = app
        self.questionList = wx.ListCtrl(self, wx.NewId(), size = wx.Size(460, 150), style=wx.LC_REPORT)
        self.questionList.InsertColumn(0, "Question")
        self.questionList.InsertColumn(1, "Sender")
        self.questionList.InsertColumn(2, "Time Sent")
        self.questionList.SetColumnWidth(0, 150)
        self.questionList.SetColumnWidth(1, 150)
        self.questionList.SetColumnWidth(2, 150)
        self.currentQuestion = wx.TextCtrl(self, -1, style= wx.TE_MULTILINE| wx.TE_READONLY)
        self.closeButton = wx.Button(self, wx.NewId(), "Close")
        self.__Layout()
        self.__PopulateQList()

        EVT_BUTTON(self, self.closeButton.GetId(), self.Close)
        EVT_LIST_ITEM_SELECTED(self, self.questionList.GetId(), self.SelectQuestion)
        
    def Close(self, event):
        '''
        Invoked when closing the window.
        '''
        self.app.Close()

    def SelectQuestion(self, event):
        '''
        Invoked when the user selects a question from the list.
        '''
        id = event.m_itemIndex
        text =  self.questionList.GetItemText(id)
        self.currentQuestion.SetValue(text)
        
    def Update(self):
        '''
        Invoked when shared question tool model changes state.
        '''
        wx.CallAfter(self.__PopulateQList)
        
    def __PopulateQList(self):
        '''
        Update question list.
        '''
        questions = self.questionTool.GetAllQuestions()
        self.questionList.DeleteAllItems()
        
        j = 0

        for question in questions:
            self.questionList.InsertStringItem(j, 'item')
            self.questionList.SetStringItem(j, 0, question["text"])
            if question["clientProfile"]:
                self.questionList.SetStringItem(j, 1, question["clientProfile"])
            else:
                self.questionList.SetStringItem(j, 1, "No name specified")
            self.questionList.SetStringItem(j, 2, question["timeStamp"])
                           
            j = j + 1
         
    def __Layout(self):
        '''
        Layout ui components.
        '''
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
	sizer.Add(wx.StaticText(self, -1, "Received Questions"), 0, 
		  wx.LEFT, 10)
	sizer.Add(self.questionList, 1, wx.EXPAND| wx.ALL, 10)
        mainSizer.Add(sizer, 1, wx.EXPAND|wx.ALL, 10)

        sizer = wx.BoxSizer(wx.VERTICAL)
	sizer.Add(wx.StaticText(self, -1, "Selected Questions"), 0, 
		  wx.LEFT|wx.TOP, 10)
	sizer.Add(self.currentQuestion, 1, wx.EXPAND| wx.ALL, 10)
        mainSizer.Add(sizer, 1, wx.EXPAND|wx.ALL, 10)
      
        mainSizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND | wx.LEFT|wx.RIGHT, 5)
        mainSizer.Add(self.closeButton, 0, wx.ALIGN_CENTER| wx.ALL, 10)
        
        self.SetSizer(mainSizer)
        mainSizer.Fit(self)
        self.SetAutoLayout(1)
                 

class AudienceView(wx.Panel, Observer):
    '''
    View for an audience member allowing the user to send and view
    questions.
    '''
    def __init__(self, parent, questionTool, app):
        '''
        Create ui components.
        '''
        wx.Panel.__init__(self, parent, -1)
        Observer.__init__(self)
        self.app = app
        self.parent = parent
        self.questionTool = questionTool
        self.questionList = wx.ListCtrl(self, wx.NewId(), size = wx.Size(460, 150),style=wx.LC_REPORT)
        self.questionList.InsertColumn(0, "Questions")
        self.questionList.InsertColumn(1, "Time Sent")
        self.questionList.SetColumnWidth(0, 300)
        self.questionList.SetColumnWidth(1, 150)
        
        self.currentQuestion = wx.TextCtrl(self, -1, style= wx.TE_MULTILINE)
        self.currentQuestion.Enable()
	self.currentQuestion.SetEditable(True)
        
        self.sendButton = wx.Button(self, wx.NewId(), "Send")
        self.closeButton = wx.Button(self,  wx.ID_CLOSE, "Close")
        
        self.__Layout()
        
        EVT_BUTTON(self, self.sendButton.GetId(), self.SendQuestion)
        EVT_BUTTON(self, self.closeButton.GetId(), self.Close)
     
    def SendQuestion(self, event):
        '''
        Invoked when user clicks the send button.
        '''
        text = self.currentQuestion.GetValue()
        self.questionTool.SendQuestion(text)
        
    def Close(self, event):
        '''
        Invoked when panel is closed.
        '''
        self.app.Close()
        
    def Update(self):
        '''
        Ivoked when shared question tool model changes state.
        '''
        # Use wx.CallAfter when calling ui outside of main thread.
        wx.CallAfter(self.__PopulateQList)
        wx.CallAfter(self.currentQuestion.Clear)
        
    def __PopulateQList(self):
        '''
        Update my list of questions.
        '''
        myQuestions = self.questionTool.GetMyQuestions()
        self.questionList.DeleteAllItems()
        
        j = 0
        for question in myQuestions:
            self.questionList.InsertStringItem(j, 'item')
            self.questionList.SetStringItem(j, 0, question["text"])
            self.questionList.SetStringItem(j, 1, question["timeStamp"])
            j = j+1
             
    def __Layout(self):
        '''
        Layout ui components.
        '''
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
	sizer.Add(wx.StaticText(self, -1, "Your Sent ande Received Questions"),
		  0, wx.LEFT, 10)
	sizer.Add(self.questionList, 1, wx.EXPAND| wx.ALL, 10)
        mainSizer.Add(sizer, 1, wx.EXPAND|wx.ALL, 10)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
	sizer.Add(wx.StaticText(self, -1, "New Question"), 0, wx.LEFT|wx.TOP, 10)
	sizer.Add(self.currentQuestion, 1, wx.EXPAND| wx.ALL, 10)
        mainSizer.Add(sizer, 1, wx.EXPAND|wx.ALL, 10)
        
        mainSizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND | wx.LEFT|wx.RIGHT, 5)
         
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.sendButton, 0, wx.CENTER | wx.ALL, 10)
        sizer.Add(self.closeButton, 0, wx.CENTER | wx.ALL, 10)
        
        mainSizer.Add(sizer, 0, wx.ALIGN_CENTER)
        
        self.SetSizer(mainSizer)
        mainSizer.Fit(self)
        self.SetAutoLayout(1)
  
            
class ArgumentManager:
    '''
    Take care of command line arguments.
    '''
    def __init__(self):
        self.arguments = {}
        self.arguments['applicationUrl'] = None
        self.arguments['debug'] = 0
        
    def GetArguments(self):
        return self.arguments
        
    def Usage(self):
        """
        How to use the program.
        """
        print "%s:" % sys.argv[0]
        print "    -a|--applicationURL : <url to application in venue>"
        print "    -h|--help : print usage"
        print "    -d|--debug : print debugging output"
               
    def ProcessArgs(self):
        """
        Handle any arguments we're interested in.
        """
        try:
            opts, args = getopt.getopt(sys.argv[1:], "a:l:dh",
                                       ["applicationURL=",
                                        "debug", "help"])
        except getopt.GetoptError:
            self.Usage()
            sys.exit(2)
            
        for o, a in opts:
            if o in ("-a", "--applicationURL"):
                self.arguments["applicationUrl"] = a
            elif o in ("-d", "--debug"):
                self.arguments["debug"] = 1
            elif o in ("-h", "--help"):
                self.Usage()
                sys.exit(0)
    
        
if __name__ == "__main__":
    app = WXGUIApplication()
    name = "SharedQuestionTool"
    
    # Parse command line options
    am = ArgumentManager()
    am.ProcessArgs()
    aDict = am.GetArguments()
  
    appUrl = aDict['applicationUrl']
    debugMode = aDict['debug']

    init_args = []

    if "--debug" in sys.argv or "-d" in sys.argv:
        init_args.append("--debug")
    
    app.Initialize(name, args=init_args)
    
    if not appUrl:
        am.Usage()
    else:
        wx.InitAllImageHandlers()

        # Create Question Tool 
        qt = SharedQuestionTool(appUrl, name)

        # Create Question Tool User Interface
        uiApp = SharedQuestionToolUI(qt, qt.log)
        uiApp.MainLoop()
     
