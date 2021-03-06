#-----------------------------------------------------------------------------
# Name:        DataStoreClient.py
# Purpose:     
# Created:     2002/12/12
# RCS-ID:      $Id: DataStoreClient.py,v 1.29 2006-11-24 13:09:38 braitmai Exp $
# Copyright:   (c) 2003
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
"""
"""
__revision__ = "$Id: DataStoreClient.py,v 1.29 2006-11-24 13:09:38 braitmai Exp $"
__docformat__ = "restructuredtext en"

import sys
import os
import tempfile
import getopt
import fnmatch

from AccessGrid import Log
from AccessGrid import Platform
from AccessGrid.Platform.Config import UserConfig
from AccessGrid import DataStore
from AccessGrid.interfaces.Venue_client import VenueIW
from AccessGrid.Toolkit import Application

log = Log.GetLogger(Log.DataStoreClient)

class FileNotFound(Exception):
    pass

def GetVenueDataStore(venueURL, connectionId):
    """
    Return the default venue datastore for the given venue URL.
    """

    vproxy = VenueIW(venueURL)
    #vproxy = Client.SecureHandle(venueURL).GetProxy()
    #log.info("Connecting to venue %s, to get datastore information.", venueURL)
    
    try:
        ds = vproxy.GetDataStoreInformation()
    except:
        log.exception("Couldn't get data store information from the venue.")
        return None
    
    # Catch failed return
    if not ds:
        return None

    upload = ds[0]
    store = ds[1]

    dsc = DataStoreClient(upload, venueURL, connectionId)

    return dsc


class DataStoreFileReader:
    """
    This is a file handle lookalike class that manages the reading
    from a venue-based file.
    """

    def __init__(self, dsc, name):
        """
        Create a new venue file reader. dsc is the datastore client, name
        is the name of the file in the venue.
        """

        self.dsc = dsc
        self.name = name
        self.open = 0

        try:
            dot = name.rindex(".")
            ext = name[dot + 1:]
        except ValueError:
            ext = ""

        self.localFile = tempfile.mktemp(ext)

        try:
            self.dsc.Download(self.name, self.localFile)
        except Exception, e:
            print "DataStoreFileReader: download failed"
            raise e

        self.fh = open(self.localFile)
        self.open = 1

    def __del__(self):
        self.close()

    def close(self):

        if not self.open:
            return
        self.fh.close()
        os.unlink(self.localFile)
        self.open = 0

    def flush(self):
        pass

    def isatty(self):
        return 0

    def fileno(self):
        return self.fh.fileno()

    def read(self, size = -1):
        return self.fh.read(size)

    def readline(self, size = -1):
        return self.fh.readline(size)

    def xreadlines(self):
        return self.fh.xreadlines()

    def seek(self, offset, whence = 0):
        return self.fh.seek(offset, whence)

    def tell(self):
        return self.fh.tell()

    def truncate(self, size = 0):
        raise Exception, "truncate not implemented on venue files"

    def write(self, str):
        raise Exception, "write not implemented on readonly venue files"

    def writelines(self, seq):
        raise Exception, "writelines not implemented on readonly venue files"

    def __iter__(self):
        return self.fh.__iter__()

class DataStoreFileWriter:
    """
    This is a file handle lookalike class that manages the writing
    to a venue-based file.
    """

    def __init__(self, dsc, name):
        """
        Create a new venue file writer. dsc is the datastore client, name
        is the name of the file in the venue.
        """

        self.dsc = dsc
        self.name = name
        self.open = 0

        #
        # create a temporary directory for this file so
        # we can write it with the correct filename.
        #

        self.tempdir = os.path.join(UserConfig.instance().GetTempDir(),
                               "DSClientTemp-%s" % (os.getpid()))
        os.mkdir(self.tempdir)
        self.localFile = os.path.join(self.tempdir, name)
        print "Creating local file ", self.localFile

        self.fh = open(self.localFile, "w")
        self.open = 1

    def __del__(self):
        self.close()

    def close(self):

        if not self.open:
            return
        self.fh.close()

        self.dsc.Upload(self.localFile)
        os.unlink(self.localFile)
        os.rmdir(self.tempdir)
        self.open = 0

    def flush(self):
        pass

    def isatty(self):
        return 0

    def fileno(self):
        return self.fh.fileno()

    def read(self, size = -1):
        raise Exception, "read not implemented on readonly venue files"

    def readline(self, size = -1):
        raise Exception, "readline not implemented on readonly venue files"

    def xreadlines(self):
        raise Exception, "xreadlines not implemented on readonly venue files"

    def seek(self, offset, whence = 0):
        return self.fh.seek(offset, whence)

    def tell(self):
        return self.fh.tell()

    def truncate(self, size = None):
        return self.fh.truncate(size)

    def write(self, str):
        return self.fh.write(str)

    def writelines(self, seq):
        return self.fh.writelines(seq)

    def __iter__(self):
        return self.fh.__iter__()


class DataStoreClient:
    """
    Client interface API for a venue datastore.

    Currently we wrap the basic datastore upload/download and
    file listing methods.
    """

    def __init__(self, uploadURL, venueUrl, connectionId=None):
        self.venueUrl = venueUrl
        self.uploadURL = uploadURL
        self.venueProxy = VenueIW(venueUrl) #Client.SecureHandle(venueUrl).GetProxy()
        self.connectionId = connectionId
        self.LoadData()

    def LoadData(self):
        """
        Load the local data descriptor cache from the datastore.
        """

        descList = self.venueProxy.GetDataDescriptions()

        self.dataCache = []
        self.dataIndex = {}

        #
        # the data index is keyed on the name.
        # this will break with duplicate names, so we need
        # to fix that when that becomes possible.
        #
        if descList:

            for desc in descList:
                self.dataCache.append(desc)
                self.dataIndex[desc.name] = desc

    def QueryMatchingFilesMultiple(self, patternList):

        fnames = {}
        for pat in patternList:
            match = self.QueryMatchingFiles(pat)
            for m in match:
                fnames[m] = 1
        files = fnames.keys()

        return files

    def QueryMatchingFiles(self, pattern):
        """
        Return a list of filenames that match the given pattern.
        Pattern is a unix-style filename wildcard.
        """
        ret = []
        for data in self.dataCache:
            fname = data.name
            if fnmatch.fnmatchcase(fname, pattern):
                ret.append(str(fname))

        return ret

    def GetFileData(self, filename):
        if filename in self.dataIndex:
            return self.dataIndex[filename]
        else:
            raise FileNotFound

    def Download(self, filename, localFile):
        """
        Download filename to local file localFile.
        """

        if filename in self.dataIndex:
            data = self.dataIndex[filename]
            url = data.uri
            print "URL: " , url
            my_identity = str(Application.instance().GetDefaultSubject())
            user=str(url.split('/')[3])
            passw=str(self.connectionId)
            DataStore.DownloadFile(my_identity, url, localFile, data.size, data.checksum, user, passw)
        else:
            raise FileNotFound

    def Upload(self, localFile):
        """
        Upload localFile to the venue datastore.
        """

        try:
            #log.debug("Upload %s to %s", localFile, self.uploadURL)
            my_identity = str(Application.instance().GetDefaultSubject())
            user=str(self.uploadURL.split('/')[-1])
            passw=str(self.connectionId)
            DataStore.UploadFiles(my_identity, self.uploadURL, [localFile], user, passw)
        except DataStore.UploadFailed, e:
            #rc, errlist = e.args[0]
            #for err in errlist:
            #    print err
            raise e

    def RemoveFile(self, file):
        try:
            data = self.dataIndex[file]
            print "File=%s data=%s" % (file, data)
            # If the proxy is a data store, then this is fine, but right now
            # self.venueProxy.RemoveFiles([data])
            # the proxy is the venue, so this needs to be:
            self.venueProxy.RemoveData(data)
        except Exception, e:
            #print "Error removing data ", e
            raise e
            
    def OpenFile(self, file, mode = "r"):

        if mode == "r":
            try:
                fh = DataStoreFileReader(self, file)
            except Exception, e:
                print "Open failed", e
                fh = None
            return fh
        elif mode == "w":
            try:
                fh = DataStoreFileWriter(self, file)
            except Exception, e:
                print "Open failed", e
                fh = None
            return fh
        else:
            print "Unknown mode ", mode
            return None


import cmd
class DataStoreShell(cmd.Cmd):

    def __init__(self, dsc):
        self.dsc = dsc
        cmd.Cmd.__init__(self)
        self.prompt = "DataStore> "

    def run(self):
        self.cmdloop()


    #
    # Commands
    #

    def do_ls(self, arg):
        self.listFiles(arg)
        return 0

    def do_dir(self, arg):
        self.listFiles(arg)
        return 0

    def do_EOF(self, arg):
        return 1

    def do_quit(self, arg):
        return 1

    def emptyline(self):
        pass

    def do_more(self, arg):
        for file in arg.split():
            self.pageFile(file, "more")
        return 0

    def do_less(self, arg):
        for file in arg.split():
            self.pageFile(file, "less")
        return 0

    def do_update(self, arg):
        print "Loading data from venue..."
        self.dsc.LoadData()
        print "... done"
        return 0

    def do_lpwd(self, arg):
        print os.getcwd()
        return 0

    def do_lcd(self, arg):
        try:
            os.chdir(arg)
        except OSError, e:
            print "chdir failed: ", e.args[0]

        return 0

    def do_get(self, arg):
        self.dsc.Download(arg, arg)
        return 0

    def do_put(self, arg):
        for file in arg.split():
            if os.path.isfile(file):
                try:
                    self.dsc.Upload(arg)
                except Exception, e:
                    print "Upload failed: ", e
            else:
                print "%s is not a regular file" % (file)
        self.dsc.LoadData()
        return 0

    def do_del(self, arg):
        files = self.dsc.QueryMatchingFilesMultiple(arg.split())
        for file in files:
            self.dsc.RemoveFile(file)
        self.dsc.LoadData()
        return 0

    def do_rm(self, arg):
        return self.do_del(arg)

    def do_head(self, arg):
        files = self.dsc.QueryMatchingFilesMultiple(arg.split())
        for file in files:
            fh = self.dsc.OpenFile(file, "r")
            if fh is None:
                print "Couldn't open file ", file
                continue

            for i in range(0, 10):
                l = fh.readline()
                if l is None:
                    break
                print l,
            fh.close()

    def do_cat(self, arg):
        files = self.dsc.QueryMatchingFilesMultiple(arg.split())
        for file in files:
            fh = self.dsc.OpenFile(file, "r")
            if fh is None:
                print "Couldn't open file ", file
                continue

            for l in fh:
                print l,
            fh.close()

    def do_copystdin(self, arg):
        """
        Copy stdin to a file.
        """

        fh = self.dsc.OpenFile(arg, "w")
        print """Enter data, followed by "." on a line by itself."""
        while 1:
            l = sys.stdin.readline()
            if l.startswith(".") or l is None:
                break

            print "Read <%s>" % (l)

            fh.write(l)
        fh.close()
        self.dsc.LoadData()


    #
    # Impls
    #

    def pageFile(self, file, pager):

        try:
            dot = file.rindex(".")
            ext = file[dot + 1:]
        except ValueError:
            ext = ""

        localFile = tempfile.mktemp(ext)

        try:
            self.dsc.Download(file, localFile)
            if Platform.IsWindows() and pager == "more":
                os.system("more < %s" % (localFile))
            else:
                os.system("%s %s" % (pager, localFile))
            os.unlink(localFile)
        except Exception, e:
            print "Except! ", e

    def listFiles(self, arg):

        verb = 0
        url = 0

        try:
            opts, args = getopt.getopt(arg.split(), "lu")
        except getopt.GetoptError:
            print "Unknown argument"
            return

        for opt, optarg in opts:
            if opt == "-l":
                verb = 1
            if opt == "-u":
                url = 1

        if args == []:
            args.append("*")

        files = self.dsc.QueryMatchingFilesMultiple(args)

        files.sort()
        for f in files:
            if verb and url:
                data = self.dsc.GetFileData(f)
                print "%-20s %10s %-12s %s" % (f, data.size, data.type, data.uri)
            elif verb:
                data = self.dsc.GetFileData(f)
                print "%-20s %10s %s " % (f, data.size, data.type)
            elif url:
                data = self.dsc.GetFileData(f)
                print "%-20s %s" % (f, data.uri)
            else:
                print f

class RemoteFileObj:
    """
    Class to represent an individual file or directory from
    the remote side.
    """

    TYPE_DIR = "dir"
    TYPE_FILE = "file"

    def __init__(self, name, url, size, type):
        self.name = name
        self.size = size
        self.type = type
        self.url = url

    def __repr__(self):
        if self.type == self.TYPE_DIR:
            ret = "Directory: "
        else:
            ret = "File:      "

        ret += "%s %s %s" % (self.name, self.size, self.url)

        return ret


if __name__ == "__main__":
    Application.instance().Initialize("DataStoreClient")

    def testData(vurl,connectionId):

        dsc = GetVenueDataStore(vurl,connectionId)

        sh = DataStoreShell(dsc)
        sh.run()
        
    hdlr = Log.StreamHandler()
    hdlr.setLevel(Log.ERROR)
    Log.HandleLoggers(hdlr, Log.GetDefaultLoggers())

    if len(sys.argv) > 1 and sys.argv[1] == "-d":
        hdlr.setLevel(Log.DEBUG)
        del sys.argv[1]
        
    url = sys.argv[1]
    connectionId = sys.argv[2]
    testData(url,connectionId)
