import wx
import types

class CertificateBrowserBase(wx.Panel):
    """
    Base class for certificate browser panels.

    This class defines the look and feel (a wx.ListCtrl in report mode, with
    buttons alongside whose state may change depending on which certificate
    is selected) and manages the list of certificates.

    Subclasses define the loading mechanism for the browser, the list of columns,
    and per-cert formatting.

    """
    
    def __init__(self, parent, id, certMgr):

        self.certMgr = certMgr

        wx.Panel.__init__(self, parent, id)

        self.__build()

        certMgr.GetCertificateRepository().RegisterObserver(self.OnRepoUpdate)

        self.Load()

    def OnRepoUpdate(self, repo):
        self.Load()

    def Load(self):
        """
        The Load method causes the browser to reload from its data source,
        clearing out the previous contents first.

        """

        #
        # Determine if we had a selection before; if so we'd like
        # to retain it.
        #

        selectedItems = []
        indices = self._getSelectedIndices()
        for idx in indices:
            item = self._getListItem(idx)
            selectedItems.append(item)


        #
        # Clear out the list..
        #
        
        self._clearList()


        #
        # ... and reload.
        #

        certs = self._LoadCerts()

        #
        # If we didn't get any certs, set the listctrl
        # to autosize from teh headers so we can see what would have been there.
        #

        if len(certs) == 0:
            sizes = self._getListColumnWidths()
            for col in range(0, len(sizes)):
                self.list.SetColumnWidth(col, wx.LIST_AUTOSIZE_USEHEADER)
            return

        #
        # Format each cert. Format means to retrieve the
        # list of column values for this certificate, as well
        # as an object that will be bound to the data for the
        # row.
        #



        row = 0
        for cert in certs:
            data, columnStrings = self._FormatCert(cert)
            id = self._addListItem(data)

            val = columnStrings[0]
            self._insertListItem(row, val)
            col = 1
            for val in columnStrings[1:]:
                self._setListItem(row, col, val)
                col += 1

            #
            # Remember the data.
            #
            self.list.SetItemData(row, id)

            row += 1

        sizes = self._getListColumnWidths()
        for col in range(0, len(sizes)):
            self.list.SetColumnWidth(col, sizes[col])
            

    def __build(self):
        #
        # Construct the GUI.
        #
        # self.sizer is the overall hsizer
        # self.list is the list control widget living in self.sizer
        # bsizer is the vsizer that holds the buttons.
        #
        # We invoke _buildButtons to fill in the button sizer; to be
        # provided by our subclass.
        #
        # We also invoke _configList to configure the list control.
        #
        # If a subclass wishes to add somethign below the list control, it
        # can define _buildExtra(parent, sizer), where parent is the
        # parent panel for any extra widgets, and sizer is the overall
        # vsizer to which the extra-builder should add its widgets.
        #

        self.topsizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.list = wx.ListCtrl(self, -1, style = wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VRULES)
        self.sizer.Add(self.list, 1, wx.EXPAND)

        wx.EVT_LIST_ITEM_SELECTED(self.list, self.list.GetId(),
                               self.OnListItemSelected)
        wx.EVT_LIST_ITEM_DESELECTED(self.list, self.list.GetId(),
                               self.OnListItemDeselected)
        wx.EVT_LIST_ITEM_ACTIVATED(self.list, self.list.GetId(),
                                self.OnListItemActivated)

        bsizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(bsizer, 0, wx.EXPAND)

        self._buildButtons(bsizer)

        self.topsizer.Add(self.sizer, 1, wx.EXPAND)
        self._buildExtra(self, self.topsizer)
        
        self._initList()

        self.SetSizer(self.topsizer)
        self.SetAutoLayout(1)
        self.Fit()

    def _initList(self):
        """
        Initialize the columns for the listctrl.
        Uses the _getListColumns() method to determine the
        columns needed.
        """

        cols = self._getListColumns() 
        idx = 0

        for c in cols:
            self.list.InsertColumn(idx, c)
            idx += 1

        #
        # Initialize the dict used for mapping item identifier
        # to item data.
        #

        self.listItemMap = {}

    def OnListItemSelected(self, event):
        row = event.m_itemIndex

        data = self._getListItem(row)
        self.OnCertSelected(event, data)

    def OnListItemDeselected(self, event):
        row = event.m_itemIndex

        data = self._getListItem(row)

        self.OnCertDeselected(event, data)

    def OnListItemActivated(self, event):
        row = event.m_itemIndex

        data = self._getListItem(row)

        self.OnCertActivated(event, data)

    def GetSelectedCertificate(self):
        sel = self._getSelectedIndices()
        if len(sel) == 0:
            return None

        item = self._getListItem(sel[0])
        return item

    def _clearList(self):
        self.list.DeleteAllItems()
        self.listItemMap.clear()

    def _insertListItem(self, row, val):
        """
        Wrapper for list.InsertItem flavors that handles
        other, non-string, types that we support.
        """

        if type(val) in types.StringTypes:
            self.list.InsertStringItem(row, val)
        elif type(val) == types.TupleType:
            itemType = val[0]
            itemVal = val[1]

            isImage, item = self._formatListItem(itemType, itemVal)

            if isImage:
                self.list.InsertImageItem(row, item)
            else:
                self.list.InsertStringItem(row, item)

    def _setListItem(self, row, col, val):
        """
        Wrapper for list.SetItem flavors that handles
        other, non-string, types that we support.
        """

        if type(val) in types.StringTypes:
            self.list.SetStringItem(row, col, val)
        elif type(val) == types.TupleType:
            itemType = val[0]
            itemVal = val[1]

            isImage, val = self._formatListItem(itemType, itemVal)

            self.list.SetStringItem(row, col, val)

    def _formatListItem(self, type, val):
        if type == "bool":
            if val:
                res = "T"
            else:
                res = "F"

            return 0, res
        else:
            return 0, val

    def _addListItem(self, item):
        """
        Create a new list item. This assigns an id,
        adds the mapping, and returns the new id.
        """
        
        id = self._getNewItemId()
        self.listItemMap[id] = item
        return id

    def _getListItem(self, row):

        id = self.list.GetItemData(row)
        return self.listItemMap[id]

    def _getNewItemId(self):
        return wx.NewId();

    def _getSelectedIndices(self, state =  wx.LIST_STATE_SELECTED):
        indices = []
        found = 1
        lastFound = -1
        while found:
            index = self.list.GetNextItem(lastFound,
                                          wx.LIST_NEXT_ALL,
                                          state,
                                          )
            if index == -1:
                break
            else:
                lastFound = index
                indices.append( index )
        return indices
    

    #
    # Following are the methods meant to be overridden.
    #

    def _buildButtons(self, sizer):
        #
        # Default implementation.
        #

        b = wx.Button(self, -1, "FOo")
        sizer.Add(b, 0, wx.EXPAND)

    def _buildExtra(self, panel, sizer):
        """
        Build more stuff in the bottom of the browser panel.

        @param panel: Panel to use as parent of any new widgets.
        @param sizer: Sizer to which the widgets should be added. It's the
        vbox that holds the overall panel.

        """

        pass

    def _getListColumns(self):
        """
        Return the column names for this browser.
        Meant to be overridden by subclass.
        """

        return ["test 1", "test 2", "test 3"]
        
    def _getListColumnWidths(self):
        return [wx.LIST_AUTOSIZE, wx.LIST_AUTOSIZE, wx.LIST_AUTOSIZE]

    def _LoadCerts(self):
        """
        Load the certificates for the browser.
        """

        return ['cert1', 'cert2', 'cert3', 'cert4']

    def _FormatCert(self, cert):
        data = [cert]
        # cols = [("bool", cert == "cert2"), cert, cert.swapcase()]
        cols = [cert, cert.swapcase(), ("bool", cert == "cert2")]
        return data, cols

    def OnCertActivated(self, event, cert):
        pass

    def OnCertSelected(self, event, cert):
        pass

    def OnCertDeselected(self, event, cert):
        pass

