#-----------------------------------------------------------------------------
# Name:        Utilities.py
# Purpose:
#
# Author:      Everyone
#
# Created:     2003/23/01
# RCS-ID:      $Id: Utilities.py,v 1.47 2003-09-18 14:55:06 lefvert Exp $
# Copyright:   (c) 2003
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
"""
"""

__revision__ = "$Id: Utilities.py,v 1.47 2003-09-18 14:55:06 lefvert Exp $"
__docformat__ = "restructuredtext en"

import os
import string
import sys
import traceback
import ConfigParser
import time
from random import Random
import sha
import urllib
import urlparse
from threading import Lock, Condition

import logging
log = logging.getLogger("AG.Utilities")

from AccessGrid.Platform import GetUserConfigDir

# Global variables for sending log files
VENUE_CLIENT_LOG = 0
VENUE_MANAGEMENT_LOG = 1
NODE_SETUP_WIZARD_LOG = 2
NO_LOG = 3


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
            rconfig[sec + separator + opt] = string.strip(cp.get(sec, opt, 1))
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
            if option != "None":
                cp.set(section, option, value)
        except:
            print "Couldn't set option."

    try:
        outFile = file(fileName, 'w+')
    except IOError, e:
        print "Couldn't open file for writing, database mods lost."
        return

    cp.write(outFile)
    outFile.close()
    
def formatExceptionInfo(maxTBlevel=5):
    cla, exc, trbk = sys.exc_info()
    excName = cla.__name__
    try:
        excArgs = exc.__dict__["args"]
    except KeyError:
        excArgs = "<no args>"
    excTb = traceback.format_tb(trbk, maxTBlevel)
    return (excName, excArgs, excTb)

def GetRandInt(r):
    return int(r.random() * sys.maxint)
    
def AllocateEncryptionKey():
    """
    This function returns a key that can be used to encrypt/decrypt media
    streams.    
    
    Return: string
    """
    
    # I know that the python documentation says the builtin random is not
    # cryptographically safe, but 1) our requirements are not fort knox, and 2)
    # the random function is being upgraded to a better version in Python 2.3
        
    rg = Random(time.time())
    
    intKey = GetRandInt(rg)
    
    for i in range(1, 8):
        intKey = intKey ^ rg.randrange(1, sys.maxint)

#    print "Key: %x" % intKey
    
    return "%x" % intKey

def GetResourceList( resourceFile ):
    """
    This method reads a file generated by vic and a tcl script
    (courtesy Bob Olson) which contains a vic-compatible description
    of video capture devices on the local machine.  
    Note:  the name of the file is hardcoded
    Note:  for now, the file should be generated at installation, and the
            user should be provided with instructions for generating the 
            file by hand.
           later, users should be able to force generation of the file
            from within the AG software

    An example of the file is as follows:

        device: o100vc.dll - Osprey Capture Card 2
        portnames:  external-in 
        device: Microsoft WDM Image Capture (Win32)
        portnames:  external-in 
        device: o100vc.dll - Osprey Capture Card 1
        portnames:  external-in 

    Note: there's a bad assumption here: the caller specifies the resources
    file; if it's not found, we generate the resource file in the location
    that the system expects.  This should be fixed, and it's on my list. -Tom

    """
    from AccessGrid.Types import Capability, AGVideoResource
    import fileinput
    import re

    resources = []

    oDeviceMatch = re.compile("^device: (.*)")
    oPortnameMatch = re.compile("^portnames:  (.*[^\s])")

    device = None
    portnames = None

    # Read the file if it exists
    if os.path.exists(resourceFile):
        for line in fileinput.input(files = [resourceFile ] ):
            match = oDeviceMatch.match(line)
            if match != None:
                device = match.groups()[0]
            match = oPortnameMatch.match(line)
            if match != None:
                portnames = string.split( match.groups()[0], ' '  )

                # assume that, if we have portnames, we already have a device
                resources.append( AGVideoResource( Capability.VIDEO, device,
                                                   Capability.PRODUCER, portnames ) )
    else:
        print "Video resources file not found; run SetupVideo.py"

    return resources

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
              
        logFile = file(os.path.join(GetUserConfigDir(), logFileName))
        
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
    
    except Exception,e:
        #
        # If reading the log file failed somehow, the text sent in the
        # error report contains the received error message
        #
        (name, args, traceback_string_list) = formatExceptionInfo()
        
        traceback = ""
        for x in traceback_string_list:
            traceback += x + "\n"

  
        #info = "\n\n"+"Type: "+str(sys.exc_type)+"\n"+"Value: "+str(sys.exc_value) + "\nTraceback:\n" + traceback
        text = logFileName + " could not be located " #+ info # text for error report

    #
    # Seek for todays date to just include relevant
    # log messages in the error report
    #
    
    todaysDate = time.strftime("%m/%d/%Y", time.localtime())
    dateIndex = text.find(str(todaysDate))
    
    if dateIndex != -1:
        #
        # If today's date is found, send log info starting from that index.
        # Else, the last "maxSize" bytes of the log file is sent
        #
        
        text = text[dateIndex:]

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
    args['product'] = "Virtual Venues Client Software"
    args['version'] = "2.1.1"
    args['component'] = "Client UI"
    args['rep_platform'] = "Other"
    
    #
    # This detection can get beefed up a lot; I say
    # NT because I can't tell if it's 2000 or XP and better
    # to not assume there.
    #
    # cf http://www.lemburg.com/files/python/platform.py
    #
    
    if sys.platform.startswith("linux"):
        args['op_sys'] = "Linux"
    elif sys.platform == "win32":
        args['op_sys'] = "Windows NT"
    else:
        args['op_sys'] = "other"
        
    args['priority'] = "P2"
    args['bug_severity'] = "normal"
    args['bug_status'] = "NEW"
    args['assigned_to'] = ""
    args['cc'] = "lefvert@mcs.anl.gov"   # email to be cc'd
    args['bug_file_loc'] = "http://"
    
    
    args['submit'] = "    Commit    "
    args['form_name'] = "enter_bug"
    
   
    
    #
    # Combine comment, profile, and log file information
    #

        
    if profile:
        # Always set profile email to empty string so we don't write to wrong email address.
        profile.email = ""
        profileString = str(profile)

    else:
        profileString = "This reporter does not have a client profile"
        
    if email == "":
        # This reporter does not want to be contacted. Do not submit email address.
        email = "This reporter does not want to be contacted.  No email address specified."

        
    commentAndLog = "\n\n--- EMAIL TO CONTACT REPORTER ---\n\n" + str(email) \
                    +"\n\n--- REPORTER CLIENT PROFILE --- \n\n" + profileString \
                    +"\n\n--- COMMENT FROM REPORTER --- \n\n" + comment 


    if logFile == NO_LOG:
        args['short_desc'] = "Feature or bug report from menu option"
        
    
    elif logFile == VENUE_MANAGEMENT_LOG:
        args['short_desc'] = "Crash in Venue Management UI"
        commentAndLog = commentAndLog \
                        +"\n\n--- VenueManagement.log INFORMATION ---\n\n"+GetLogText(20000, "VenueManagement.log")
        
    elif logFile == NODE_SETUP_WIZARD_LOG:
        args['short_desc'] = "Crash in Node Setup Wizard UI"
        commentAndLog = commentAndLog \
                        +"\n\n--- NodeSetupWizard.log INFORMATION ---\n\n"+GetLogText(20000, "NodeSetupWizard.log")

    else:
        args['short_desc'] = "Crash in Venue Client UI"
        commentAndLog = commentAndLog \
                        +"\n\n--- VenueClient.log INFORMATION ---\n\n"+GetLogText(20000, "VenueClient.log") \
                        +"\n\n--- agns.log INFORMATION ---\n\n"+GetLogText(20000, "agns.log")\
                        +"\n\n--- agsm.log INFORMATION ---\n\n"+GetLogText(20000, "agsm.log")\
                        +"\n\n--- AGService.log INFORMATION ---\n\n"+GetLogText(20000, "AGService.log")

    
    args['comment']= commentAndLog
      
    #
    # Now submit to the form.
    #
    
    params = urllib.urlencode(args)
    
    f = urllib.urlopen(url, params)
    
    #
    # And read the output.
    #
    
    out = f.read()
    f.close()
        
    o = open("out.html", "w")
    o.write(out)
    o.close()
#
# We use this import to get a reliable hostname; should be made more
# general later (in the event we are using something other than hosting.pyGlobus
#

try:
    import AccessGrid.hosting.pyGlobus.Utilities
    GetHostname = AccessGrid.hosting.pyGlobus.Utilities.GetHostname
except ImportError:
    import socket
    GetHostname = socket.getfqdn()

# def StartDetachedProcess(cmd):
#     """
#     Start cmd as a detached process.

#     We start the process using a command processor (cmd on windows,
#     sh on linux).
#     """

#     if AccessGrid.Platform.isWindows():
#         shell = os.environ['ComSpec']
#         shcmd = [shell, "/c", cmd]
#         os.spawnv(os.P_NOWAIT, shell, shcmd)
#     else:
#         shell = "sh"
#         shcmd = [shell, "-c", cmd]
#         os.spawnvp(os.P_NOWAIT, shell, shcmd)

def PathFromURL(URL):
    """
    """
    return urlparse.urlparse(URL)[2]

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
            file = c[0]
            line = c[1]
            log.debug("Try to acquire server lock %s...      %s:%s", self.name, file, line)

        self.lock.acquire()

        if self.verbose:
            log.debug("Try to acquire server lock %s...done  %s:%s", self.name, file, line)

    def release(self):
        if self.verbose:
            c = (traceback.extract_stack())[-2]
            file = c[0]
            line = c[1]
            log.debug("Releasing server lock %s  %s:%s", self.name, file, line)
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

if __name__ == "__main__":
    SubmitBug("This is just a test for the Bug Reporting Tool")
