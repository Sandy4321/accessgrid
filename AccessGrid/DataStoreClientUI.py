#-----------------------------------------------------------------------------
# Name:        DataStoreClientUI.py
# Purpose:     
#
# Author:      Robert D. Olson
#
# Created:     2002/12/12
# RCS-ID:      $Id: DataStoreClientUI.py,v 1.5 2007-09-18 20:45:13 turam Exp $
# Copyright:   (c) 2003
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
"""
"""
__revision__ = "$Id: DataStoreClientUI.py,v 1.5 2007-09-18 20:45:13 turam Exp $"
__docformat__ = "restructuredtext en"

from AccessGrid import DataStoreClient

import wx

class DataStoreFileChooser:
    def __init__(self, datastoreClient, pattern = "*", message = "", caption = ""):

        self.datastoreClient = datastoreClient

        filenames = self.datastoreClient.QueryMatchingFiles(pattern)
        print "Got filenames ", filenames
        self.dlg = wx.SingleChoiceDialog(None, message, caption, filenames)

    def run(self):
        ret = self.dlg.ShowModal()

        print "Returned ", ret

        file = None

        if ret == wx.ID_OK:
            file = self.dlg.GetStringSelection()

        self.dlg.Destroy()
        return file

if __name__ == "__main__":

    app = wx.PySimpleApp()

    if len(sys.argv) < 2:
        url = "https://localhost:8000/Venues/default"
    else:
        url = sys.argv[1]
    dsc = DataStoreClient.GetVenueDataStore(url)

    dlg = DataStoreFileChooser(dsc, "*.ppt", "Choose a powerpoint file")

    file = dlg.run()
    print "You chose ", file

    dlg = DataStoreFileChooser(dsc, "*", "Choose any file", "Pick one")

    file = dlg.run()
    print "You chose ", file
