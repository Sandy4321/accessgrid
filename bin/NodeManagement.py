#!/usr/bin/python2
#-----------------------------------------------------------------------------
# Name:        NodeManagement.py
# Purpose:     
# Created:     2003/08/02
# RCS-ID:      $Id: NodeManagement.py,v 1.24 2004-03-17 21:40:08 judson Exp $
# Copyright:   (c) 2002-2003
# Licence:     See COPYING.txt
#-----------------------------------------------------------------------------
import os
import sys

from wxPython.wx import *

from AccessGrid.NodeManagementUIClasses import NodeManagementClientFrame
from AccessGrid.Toolkit import WXGUIApplication

log = None

class MyApp(wxApp):
    global log

    defNSUrl = "https://localhost:11000/NodeService"

    def OnInit(self):
        frame = NodeManagementClientFrame(NULL, -1,
                                          "Access Grid Node Management")
        try:
            frame.AttachToNode(defNSUrl)
            # Avoid UI errors if fail to attach to node.
            if frame.nodeServiceHandle.IsValid():
                frame.UpdateUI()
        except:
            if log is not None:
                log.exception("Error connecting to Node Service: %s",
                              self.defNSUrl)

        frame.Show(true)
        self.SetTopWindow(frame)

        return true

def main():
    global log
    
    wxInitAllImageHandlers()

    app = WXGUIApplication()

    try:
        app.Initialize("NodeManagement")
    except Exception, e:
        print "Toolkit initialization failed."
        print " Initialization Error: ", e
        sys.exit(-1)

    log = app.GetLog()
    
    nodeMgmtApp = MyApp(0)
    
    nodeMgmtApp.MainLoop()

if __name__ == "__main__":
    main()
