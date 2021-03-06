#-----------------------------------------------------------------------------
# Name:        Utilities.py
# Purpose:
#
# Author:      Everyone
#
# Created:     2003/23/01
# RCS-ID:      $Id: Utilities.py,v 1.89 2007-08-15 19:20:27 eolson Exp $
# Copyright:   (c) 2003
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
"""
"""

__revision__ = "$Id: Utilities.py,v 1.89 2007-08-15 19:20:27 eolson Exp $"

import os
import string
import sys
import traceback
import ConfigParser
import time
from random import Random
import urllib
from threading import Lock, Condition
import re
import urlparse
import urllib2
import zipfile

from AccessGrid import Log
log = Log.GetLogger(Log.Utilities)

from AccessGrid.Version import GetVersion, GetStatus
from AccessGrid import Platform
from AccessGrid.Platform import Config

# Global variables for sending log files
VENUE_CLIENT_LOG = 0
VENUE_MANAGEMENT_LOG = 1
NODE_SETUP_WIZARD_LOG = 2
NO_LOG = 3

def formatExceptionInfo(maxTBlevel=5):
    cla, exc, trbk = sys.exc_info()
    excName = cla.__name__
    try:
        excArgs = exc.__dict__["args"]
    except KeyError:
        excArgs = "<no args>"
    excTb = traceback.format_tb(trbk, maxTBlevel)
    return (excName, excArgs, excTb)


def LoadConfig(fileName, config=dict(), separator="."):
    """
    Returns a dictionary with keys of the form <section>.<option>
    and the corresponding values.
    This is from the python cookbook credit: Dirk Holtwick.
    """
    rconfig = config.copy()
    cp = ConfigParser.ConfigParser()
    cp.optionxform = str
    cp.read(fileName)
    for sec in cp.sections():
        for opt in cp.options(sec):
            value = string.strip(cp.get(sec, opt, 1))
            if value != "None":
                rconfig[sec + separator + opt] = value
    return rconfig

def SaveConfig(fileName, config, separator="."):
    """
    This method saves the current configuration out to the specified file.
    """
    cp = ConfigParser.ConfigParser()
    cp.optionxform = str
    section = ""
    option = ""
    value = ""
    for k in config.keys():
        if k.find(separator) != -1:
            (section, option) = k.split(separator)
        value = config[k]
        if not cp.has_section(section):
            try:
                cp.add_section(section)
            except:
                print "Couldn't add section."
        try:
            if option != "None" and value is not None:
                cp.set(section, option, value)
        except:
            print "Couldn't set option."

    try:
        outFile = file(fileName, 'w+')
    except IOError:
        print "Couldn't open file for writing, database mods lost."
        return

  
    outFile.write("# AGTk %s\n" % (GetVersion()))

    cp.write(outFile)
    outFile.close()

def GetRandInt(r):
    return int(r.random() * sys.maxint)
    
def AllocateEncryptionKey():
    """
    This function returns a key that can be used to encrypt/decrypt media
    streams.    
    
    Return: string
    """
    rg = Random(time.time())
    
    intKey = GetRandInt(rg)

    for i in xrange(8):
        intKey = intKey ^ rg.randrange(i, sys.maxint)

    return "Rijndael/%x" % intKey

def GetLogText(maxSize, logFileName):
    '''
    Reads log records, based on todays date, from log file.  

    **Arguments:**
    
    *logFileName* Name of log file to read from.
    *maxSize* The maximum number of bytes we want to read from the log file.
      
    **Returns:**
    
    *test* a string including log records from todays date.
    If the log file is missing, GetLogText will return the error message
    received when trying to read the file.  If the log file does not include any
    records from today, the last "maxSize" bytes of the file will be included in the string.
    '''
        
    try:
        #
        # Try to get text from the log file.
        #

        userConfig = Config.UserConfig.instance()
        logDir = userConfig.GetLogDir()
                
        logFile = file(os.path.join(logDir, logFileName))
        
        #
        # Move to a position "maxSize" bytes from the end of the file. 
        # The read will now just include the end of the file with a maximum
        # of "maxSize" bytes
        #
                   
        try:
            # If the file is smaller than "maxSize" this will fail
            # and the entire file will be read.
            logFile.seek(-maxSize, 2)
           
        except:
            # Start from beginning of file again
            logFile.seek(0)

        text = logFile.read(maxSize) # text for error report             
        logFile.close()

    
    except Exception:
        # If reading the log file failed somehow, the text sent in the
        # error report contains the received error message
        (name, args, traceback_string_list) = formatExceptionInfo()
        
        traceback = ""
        for x in traceback_string_list:
            traceback += x + "\n"

  
        text = logFileName + " could not be located "

    return text

def SubmitBug(comment, profile, email, logFile = VENUE_CLIENT_LOG):
    """
    Submits a bug to bugzilla. 

    **Parameters**
      *comment* = Bug description from reporter
      *profile* = Client Profile describing reporter
      *email* = Entered email address for support information. If the email
                is blank, the reporter does not want to be contacted.
    """
     
    url = "http://bugzilla.mcs.anl.gov/accessgrid/post_bug.cgi"
    args = {}

    bugzilla_login = 'client-ui-bugzilla-user@mcs.anl.gov'
    bugzilla_password = '8977f68349f93fead279e5d4cdf9c3a3'

    args['Bugzilla_login'] = bugzilla_login
    args['Bugzilla_password'] = bugzilla_password
    version = '%s %s' % (str(GetVersion()),str(GetStatus()))
    version = version.strip()
    args['version'] = version
    args['rep_platform'] = "Other"
    
    #
    # This detection can get beefed up a lot; I say
    # NT because I can't tell if it's 2000 or XP and better
    # to not assume there.
    #
    # cf http://www.lemburg.com/files/python/platform.py
    #
    
    if Platform.IsLinux():
        args['op_sys'] = "Linux"
        args['rep_platform'] = "All"  # Need a better check for this.
    elif Platform.IsWindows():
        args['op_sys'] = "Windows NT"
        args['rep_platform'] = "PC"
    elif Platform.IsOSX():
        args['op_sys'] = "MacOS X"
        args['rep_platform'] = "Macintosh"
    else:
        args['op_sys'] = "other"
        
    args['priority'] = "P2"
    args['bug_severity'] = "normal"
    args['bug_status'] = "NEW"
    args['assigned_to'] = ""
    args['cc'] = "turam@mcs.anl.gov"   # email to be cc'd
    args['bug_file_loc'] = "http://"
    
    
    args['submit'] = "    Commit    "
    args['form_name'] = "enter_bug"
    
    # Combine comment, profile, and log file information

    userConfig = Config.UserConfig.instance()
       
    # Get config information
    configData =  "\n%s" % userConfig
    configData += "\n%s\n" % Config.SystemConfig.instance()

    # Defaults.
    args['product'] = "Virtual Venues Client Software"
    args['component'] = "Client UI"
    logToSearch = None

    if profile:
        # Always set profile email to empty string so we don't write
        # to wrong email address.
        profile.email = ""
        profileString = str(profile)

    else:
        profileString = "This reporter does not have a client profile"
        
    if email == "":
        # This reporter does not want to be contacted. Do not submit
        # email address.
        email = "This reporter does not want to be contacted.  No email address specified."

    
    def AppendNodeLogs(text):
        text = text +"\n\n--- ServiceManager.log INFORMATION ---\n\n"+ \
               GetLogText(2000, "ServiceManager.log")\
             
        logDir = userConfig.GetLogDir()
        otherServiceLogs = os.listdir(logDir)          

        for serviceLog in otherServiceLogs:
            if serviceLog.endswith('Service.log'):
                text = text \
                       +"\n\n--- %s INFORMATION ---\n\n" % (serviceLog,)    \
                       +GetLogText(2000, serviceLog)

        return text
        
    commentAndLog = "\n\n--- EMAIL TO CONTACT REPORTER ---\n\n" + str(email) \
                +"\n\n--- REPORTER CLIENT PROFILE --- \n\n" + profileString \
                +"\n\n--- COMMENT FROM REPORTER --- \n\n" + comment 

    logText = None

    if logFile == NO_LOG:
        args['short_desc'] = "Feature or bug report from menu option"

    elif logFile == VENUE_MANAGEMENT_LOG:
        args['short_desc'] = "Automatic Bug Report - Venue Management"

        args['product'] = "Virtual Venue Server Software"
        args['component'] = "Management UI"
        
        logText = GetLogText(10000, "VenueManagement.log")
        commentAndLog = commentAndLog \
            +"\n\n--- VenueManagement.log INFORMATION ---\n\n"+ logText
        
    elif logFile == NODE_SETUP_WIZARD_LOG:
        args['short_desc'] = "Automatic Bug Report - Node Setup Wizard"

        args['product'] = "Node Management Software"
        args['component'] = "NodeSetupWizard"

        logText = GetLogText(10000, "NodeSetupWizard.log")
        commentAndLog = commentAndLog \
            +"\n\n--- NodeSetupWizard.log INFORMATION ---\n\n"+ logText

        commentAndLog = AppendNodeLogs(commentAndLog)

    else:
        args['short_desc'] = "Automatic Bug Report - Venue Client"
        logToSearch = GetLogText(10000, "VenueClient.log")
      
        commentAndLog = commentAndLog \
             +"\n\n--- VenueClient.log INFORMATION ---\n\n"+ logToSearch \

        commentAndLog = AppendNodeLogs(commentAndLog)

         
    # If we've got a logToSearch, look at it to find a exception
    # at the end.  If it has one, mark the component as Certificate
    # Management.

    if logToSearch:
        loc = logToSearch.rfind("Traceback")
        if loc >= 0:
            m = re.search(".*Exception.*", logToSearch[loc:])
            if m:
                args['component'] = "Certificate Management"

        logToSearch = None

    # Look at the end of the log and guess whether we need to mark this 
    args['comment']= configData + "\n\n" + commentAndLog
      
    # Now submit to the form.
    params = urllib.urlencode(args)

    f = urllib.urlopen(url, params)

    # And read the output.
    out = f.read()
    f.close()
       
    o = open("out.html", "w")
    o.write(out)
    o.close()

class ServerLock:
    """
    Class to be used for locking entry and exit to the venue server.
    Mostly just a wrapper around a normal lock, but adds logging support.
    """

    verbose = 0

    def __init__(self, name = ""):
        if self.verbose:
            log.debug("Create server lock %s", name)
        self.lock = Condition(Lock())
        self.name = name

    def acquire(self):
        if self.verbose:
            c = (traceback.extract_stack())[-2]
            fileName = c[0]
            line = c[1]
            log.debug("Try to acquire server lock %s...      %s:%s", self.name, fileName, line)

        self.lock.acquire()

        if self.verbose:
            log.debug("Try to acquire server lock %s...done  %s:%s", self.name, fileName, line)

    def release(self):
        if self.verbose:
            c = (traceback.extract_stack())[-2]
            fileName = c[0]
            line = c[1]
            log.debug("Releasing server lock %s  %s:%s", self.name, fileName, line)
        self.lock.release()

#
# File tree removal stuff, from ASPN recipe.
#

def _rmgeneric(path, func):
    try:
        log.debug("Remove %s with %s", path, func)
        func(path)
    except OSError, (errno, strerror):
        log.error("rmgeneric: error removing %s", path)
           
def removeall(path):

    if not os.path.isdir(path):
        return
   
    files=os.listdir(path)

    for x in files:
        fullpath=os.path.join(path, x)
        if os.path.isfile(fullpath):
            f=os.remove
            _rmgeneric(fullpath, f)
        elif os.path.isdir(fullpath):
            removeall(fullpath)
            f=os.rmdir
            _rmgeneric(fullpath, f)

#
# split_quoted borrowed from distutils.
#
# We're using it without the backslash escaping enabled
# so that we can use it for windows pathnames.
#


# Needed by 'split_quoted()'
_wordchars_re = re.compile(r'[^\'\"%s ]*' % string.whitespace)
_squote_re = re.compile(r"'(?:[^'\\]|\\.)*'")
_dquote_re = re.compile(r'"(?:[^"\\]|\\.)*"')

def split_quoted (s):
    """Split a string up according to Unix shell-like rules for quotes and
    backslashes.  In short: words are delimited by spaces, as long as those
    spaces are not escaped by a backslash, or inside a quoted string.
    Single and double quotes are equivalent, and the quote characters can
    be backslash-escaped.  The backslash is stripped from any two-character
    escape sequence, leaving only the escaped character.  The quote
    characters are stripped from any quoted string.  Returns a list of
    words.
    """
    
    # This is a nice algorithm for splitting up a single string, since it
    # doesn't require character-by-character examination.  It was a little
    # bit of a brain-bender to get it working right, though...

    s = string.strip(s)
    words = []
    pos = 0

    while s:
        m = _wordchars_re.match(s, pos)
        end = m.end()
        if end == len(s):
            words.append(s[:end])
            break

        if s[end] in string.whitespace: # unescaped, unquoted whitespace: now
            words.append(s[:end])       # we definitely have a word delimiter
            s = string.lstrip(s[end:])
            pos = 0

        else:
            if s[end] == "'":           # slurp singly-quoted string
                m = _squote_re.match(s, end)
            elif s[end] == '"':         # slurp doubly-quoted string
                m = _dquote_re.match(s, end)
            else:
                raise RuntimeError, \
                      "this can't happen (bad char '%c')" % s[end]

            if m is None:
                raise ValueError, \
                      "bad string (mismatched %s quotes?)" % s[end]

            (beg, end) = m.span()
            s = s[:beg] + s[beg+1:end-1] + s[end:]
            pos = m.end() - 2

        if pos >= len(s):
            words.append(s)
            break

    return words

def IsExecFileAvailable(file, path=None):
    """ Used to check if a command is available to be executed.
          Checks directories in the PATH variable are included.
          On windows, the current directory is included automatically.
          Note that the exact filename is required -- i.e. "python.exe"
          will be found on windows, but "python" won't. """
    if path == None:
        path = os.environ['PATH']
    # Windows always includes the current directory.
    if Platform.IsWindows():
        separatedPath = path.split(";")
        separatedPath.append(".") 
    else:
        separatedPath = path.split(":")
    for singlePath in separatedPath:
        fullpath = os.path.join(singlePath, file)
        #print "Checking full path:", fullpath
        if os.access(fullpath, os.X_OK):
            return 1
    return 0

# split_quoted ()

class InvalidZipFile(Exception):
    pass

def ExtractZip(zippath, dstpath):
    """
    Extract files from zipfile
    Requires Toolkit to be initialized.
    """
    try:
        if not os.path.exists(dstpath):
            os.mkdir(dstpath)

        zf = zipfile.ZipFile( zippath, "r" )
        filenameList = zf.namelist()
        for filename in filenameList:
            try:
                # create subdirs if needed
                pathparts = string.split(filename, '/')

                if len(pathparts) > 1:
                    temp_dir = str(dstpath)
                    for i in range(len(pathparts) - 1):
                        log.info("this is temp dir: %s"%(temp_dir))
                        log.info("this is pathparts: %s"%(pathparts))
                        temp_dir = os.path.join(temp_dir, pathparts[i])

                    if not os.access(temp_dir, os.F_OK):
                        try:
                            os.makedirs(temp_dir)
                        except:
                            log.exception("Failed to make temp dir %s"%(temp_dir))
                destfilename = os.path.join(dstpath,filename)

                # Extract the file
                # Treat directory names different than files.
                if os.path.isdir(destfilename):
                    pass  # skip if dir already exists
                elif destfilename.endswith("/"):
                    os.makedirs(destfilename) # create dir if needed
                else: # It's a file so extract it
                    filecontent = zf.read( filename )
                    f = open( destfilename, "wb" )
                    f.write( filecontent )
                    f.close()

                #print "setting permissions on file", destfilename

                # Mark the file executable (indiscriminately)
                os.chmod(destfilename,0755)

                #s = os.stat(destfilename)
                #print "%s mode %d" % (destfilename, s[0])
            except:
                from AccessGrid import Toolkit
                log.exception("Error extracting file %s"%(filename))

        zf.close()
    except zipfile.BadZipfile:
        log.exception("Bad zipfile: %s", zippath)
        raise InvalidZipFile(zippath)



if __name__ == "__main__":
    SubmitBug("This is just a test for the Bug Reporting Tool", None,
              "",logFile=NO_LOG)


def BuildServiceUrl(url,defaultproto,defaultport,defaultpath):
    # - define a mess of regular expressions for matching venue urls
    hostre = re.compile('^[\w.-]*$')
    hostportre = re.compile('^[\w.-]*:[\d]*$')
    hostportpathre = re.compile('^[\w.-]*:[\d]*/[\w/]*')
    hostpathre = re.compile('^[\w.-]*/[\w]*')
    protohostre = re.compile('^[\w]*://[\w.-]*$')
    protohostportre = re.compile('^[\w]*://[\w.-]*:[\d]*$')
    protohostportpathre = re.compile('^[\w]*://[\w.-]*:[\d]*/[\w]*')
    protohostpathre = re.compile('^[\w]*://[\w.-^/]*/[\w]*')

    if url.find('//') == -1:
        # - check for host only
        if hostre.match(url):
            host = url
            url = '%s://%s:%d/%s' % (defaultproto,host,defaultport,defaultpath)
        # - check for host:port
        elif hostportre.match(url):
            hostport = url
            url = '%s://%s/%s' % (defaultproto,hostport,defaultpath)
        elif hostportpathre.match(url):
            url = '%s://%s' % (defaultproto,url)
        elif hostpathre.match(url):
            parts = url.split('/')
            host = parts[0]
            path = '/'.join(parts[1:])
            url = '%s://%s:%d/%s' % (defaultproto,host,defaultport,path)
    else:
        if protohostre.match(url):
            protohost = url
            url = '%s:%d/%s' % (protohost,defaultport,defaultpath)
        elif protohostportre.match(url):
            print 'protohostport match'
            protohostport = url
            url = '%s/%s' % (protohostport,defaultpath)
        elif protohostportpathre.match(url):
            pass
        elif protohostpathre.match(url):
            parts = urlparse.urlparse(url)
            proto = parts[0]
            host = parts[1]
            path = parts[2]
            url = '%s://%s:%d%s' % (proto,host,defaultport,path)
    return url   

def BuildProxyURL(proxyHost=None, proxyPort=None, proxyUsername=None, proxyPassword=None):
    """Build a proxy URL access string"""
    proxyURL = ""
    
    if proxyHost:
        if proxyUsername and proxyPassword:
            if proxyPort:
                proxyURL = "http://%s:%s@%s:%s" % (proxyUsername, proxyPassword, proxyHost, proxyPort)
            else:
                proxyURL = "http://%s:%s@%s" % (proxyUsername, proxyPassword, proxyHost)
        else:
            if proxyPort:
                proxyURL = "http://%s:%s" % (proxyHost, proxyPort)
            else:
                proxyURL = "http://%s" % (proxyHost)
        

    return proxyURL

def BuildPreferencesProxyURL():
    """Build a proxy URL based on the settings in the preferences file"""
    from AccessGrid.Preferences import Preferences
    
    preferences = Preferences()
    proxyUsername = None
    proxyPassword = None
    
    proxyEnabled = int(preferences.GetPreference(Preferences.PROXY_ENABLED))
    if not proxyEnabled:
        return ""
    
    if int(preferences.GetPreference(Preferences.PROXY_AUTH_ENABLED)) == 1:
        proxyUsername = preferences.GetPreference(Preferences.PROXY_USERNAME)
        proxyPassword = preferences.GetProxyPassword()
        
    return BuildProxyURL(preferences.GetPreference(Preferences.PROXY_HOST), \
                         preferences.GetPreference(Preferences.PROXY_PORT), \
                         proxyUsername, \
                         proxyPassword)
    
def GetPreferencesProxyHandler():
    proxySupport = urllib2.ProxyHandler({"http" : BuildPreferencesProxyURL()})
    return proxySupport

def OpenURL(url):
    """
    This is a proxy-agnostic way of opening a URL and retrieving
    the response. The proxy settings are extracted from the preferences.
    If the connection fails, a dialog is opened to query the user
    for their username and password. This means users do not have to store
    their password in the preferences file, which is insecure to a determined
    attacker.
    """
    from AccessGrid.Preferences import Preferences
    from AccessGrid.UIUtilities import ProxyAuthDialog
    ID_OK = 5100 # hard-coding this for now to avoid importing wx
    
    preferences = Preferences()
    if int(preferences.GetPreference(Preferences.PROXY_ENABLED)):
        # There is a proxy set, so build the URL of the proxy
        proxySupport = urllib2.ProxyHandler({"http" : BuildPreferencesProxyURL()})
        opener = urllib2.build_opener(proxySupport, urllib2.HTTPHandler)
        urllib2.install_opener(opener)
    
    try:
        response = urllib2.urlopen(url)
    except urllib2.URLError, e:
        errorCode = 0
        
        # URLError is the superclass of HTTPError, which will return an error
        # code. URLError *won't*, so that has to be extracted with a regex
        if hasattr(e, 'code'):
            errorCode = int(e.code)
        elif hasattr(e, 'reason'):
            # This is a URLError, so extract the error code from reason.
            result = re.search("^\((\d+)", str(e.reason))
            errorCode = int(result.group(1))
            log.debug("URLlib failed: " + str(e.reason))
        
        # Technically only 407 should come up from a proxy authentication
        # failure
        if errorCode == 407:
            log.info("Proxy authentication failed for: " + url)
            
            # Only show the dialog if an authenticated proxy was enabled
            if int(preferences.GetPreference(Preferences.PROXY_AUTH_ENABLED)) == 1:
                dialog = ProxyAuthDialog(None, -1, "Check proxy authentication settings")
                dialog.SetProxyUsername(preferences.GetPreference(Preferences.PROXY_USERNAME))
                dialog.SetProxyPassword(preferences.GetProxyPassword())
                dialog.SetProxyEnabled(int(preferences.GetPreference(Preferences.PROXY_AUTH_ENABLED)))

                if dialog.ShowModal() == ID_OK:
                     preferences.SetPreference(Preferences.PROXY_ENABLED, 1)
                     preferences.SetPreference(Preferences.PROXY_USERNAME, dialog.GetProxyUsername())
                     preferences.SetProxyPassword(dialog.GetProxyPassword())
                     preferences.SetPreference(Preferences.PROXY_AUTH_ENABLED, dialog.GetProxyEnabled())
                     preferences.StorePreferences()

                     # Try again
                     return OpenURL(url)
             
        elif hasattr(e, 'reason'):
            log.debug("URLlib failed: " + str(e.reason))
            response = None
            
    return response
