
import sys
import os
import tempfile
import logging
import getopt
import fnmatch

from AccessGrid.hosting.pyGlobus import Client
from AccessGrid import DataStore
from pyGlobus import ftpClient

class FileNotFound(Exception):
    pass

def GetVenueDataStore(venueURL):
    """
    Return the default venue datastore for the given venue URL.
    """

    vproxy = Client.Handle(venueURL).GetProxy()

    ds = vproxy.GetDataStoreInformation()

    upload = ds[0]
    store = ds[1]

    dsc = DataStoreClient(upload, store)

    return dsc
    

class DataStoreClient:
    """
    Client interface API for a venue datastore.

    Currently we wrap the basic datastore upload/download and
    file listing methods.
    """

    def __init__(self, uploadURL, datastoreURL):
        self.datastoreURL = datastoreURL
        self.uploadURL = uploadURL
        self.datastoreProxy = Client.Handle(datastoreURL).GetProxy()

        self.LoadData()

    def LoadData(self):
        """
        Load the local data descriptor cache from the datastore.
        """

        descList = self.datastoreProxy.GetDataDescriptions()

        self.dataCache = []
        self.dataIndex = {}

        #
        # the data index is keyed on the name.
        # this will break with duplicate names, so we need
        # to fix that when that becomes possible.
        #
        
        for desc in descList:
            ddict = desc._asdict
            self.dataCache.append(ddict)
            self.dataIndex[str(ddict['name'])] = ddict

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
            fname = data['name']
            if fnmatch.fnmatch(fname, pattern):
                ret.append(str(fname))

        return ret

    def GetFileData(self, filename):
        return self.dataIndex[filename]

    def Download(self, filename, localFile):
        """
        Download filename to local file localFile.
        """

        if filename in self.dataIndex:
            data = self.dataIndex[filename]
            url = data['uri']
            print "Downloading ", url
            DataStore.GSIHTTPDownloadFile(url, localFile, data['size'], data['checksum'])
        else:
            raise FileNotFound

    def Upload(self, localFile):
        """
        Upload localFile to the venue datastore.
        """

        try:
            DataStore.GSIHTTPUploadFiles(self.uploadURL, [localFile], None)
        except DataStore.UploadFailed, e:
            rc, errlist = e.args[0]
            for err in errlist:
                print err

    def RemoveFile(self, file):
        try:
            data = self.dataIndex[file]
            self.datastoreProxy.RemoveFiles([data])
        except:
            print "Error removing data ", e


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
        self.dsc.Upload(arg)
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
            if sys.platform == 'win32' and pager == "more":
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
                print "%-20s %5s %-12s %s" % (f, data['size'], data['type'], data['uri'])
            elif verb:
                data = self.dsc.GetFileData(f)
                print "%-20s %5s %s " % (f, data['size'], data['type'])
            elif url:
                data = self.dsc.GetFileData(f)
                print "%-20s %s" % (f, data['uri'])
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

class FtpDataStoreClient:

    def __init__(self, datastoreURL):

        self.url = datastoreURL
        self.cwd = "/"
        self.ftp = ftpClient.EasyFtpClient()

    def _getURL(self, path):
        url = self.url + path
        print "get: %s %s %s " % (self.url, path, url)
        return url

    def listdir(abspath):

        ret = []
        out = self.ftp.verbose_list(self._getURL(self.cwd))

        if self.cwd == "/":
            pathbase = "/"
        else:
            pathbase = self.cwd + "/"

        for line in out.split("\n"):

            parts = line.split()
            if len(parts) > 2:
                directory = parts[0].startswith("d")
                symlink = parts[0].startswith("l")
                size = int(parts[4])
                filename = parts[-1]

                url = self._getURL(pathbase + filename)
                
                if directory:
                    obj = RemoteFileObj(filename,
                                        url,
                                        size,
                                        RemoteFileObj.TYPE_DIR)
                elif not symlink:
                    obj = RemoteFileObj(filename,
                                        url,
                                        size,
                                        RemoteFileObj.TYPE_FILE)
                ret.append(obj)

        return ret

if __name__ == "__main__":

    def testFtp():
        c = FtpDataStoreClient("gsiftp://jglobus.lcrc.anl.gov/")
        for x in c.listdir():
            print x

    def testData(vurl):

        dsc = GetVenueDataStore(vurl)

        sh = DataStoreShell(dsc)
        sh.run()

        ppt = dsc.QueryMatchingFiles("*.ppt")
        print "Ppt: ", ppt

        dsc.Download(ppt[0], "\\temp\\foo.ppt")
        dsc.Upload("\\temp\\foo.ppt")

#    logging.root.addHandler(logging.StreamHandler())
#    logging.root.setLevel(logging.ERROR)

    testData("https://localhost:8000/Venues/default")

