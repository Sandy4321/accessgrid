#-----------------------------------------------------------------------------
# Name:        ProcessManager.py
# Purpose:     
#
# Author:      Robert D. Olson
#
# Created:     2003/08/02
# RCS-ID:      $Id: ProcessManager.py,v 1.1 2004-03-05 16:26:24 eolson Exp $
# Copyright:   (c) 2002-2004
# Licence:     See COPYING.txt
#-----------------------------------------------------------------------------
"""
"""
__revision__ = "$Id: ProcessManager.py,v 1.1 2004-03-05 16:26:24 eolson Exp $"
__docformat__ = "restructuredtext en"

import signal
import os
import time
import logging

log = logging.getLogger("AG.ProcessManager")

class ProcessManager:

    def __init__(self):
        self.processes = []

    def start_process(self, command, arglist):
        """
        Start a new process.
        Command is the name of the command to be started. It can either be
        a full pathname or a command name to be found on the default path.
        Arglist is a list of the arguments to the command.
        """

        arglist.insert(0, command)

        arglist = map(lambda a: str(a), arglist)
        pid = os.spawnvp(os.P_NOWAIT, command, arglist)

        self.processes.append(pid)

        return pid

    def terminate_all_processes(self):
        for pid in self.processes:
            try:
                self._terminate_process(pid)   
            except OSError, e:
                log.debug( "couldn't terminate process: %s", e )

        self.processes = []

    def terminate_process(self, pid):
        try:
            self._terminate_process(pid)    
            self.processes.remove(pid)
        except OSError, e:
            log.debug ( "couldn't terminate process: %s", e )
    
    def _terminate_process(self, pid):
        os.kill(pid, signal.SIGINT)
        elapsedWaits = 0
        maxWaits = 5
        waitTime = 1
        retpid = 0
        try:
            while elapsedWaits < maxWaits:
                (retpid,status) = os.waitpid(pid, os.WNOHANG )
                #print "waitpid returns ", retpid, status
                if retpid == pid and os.WIFEXITED(status):
                    break
                time.sleep(waitTime)
                elapsedWaits += 1
        except OSError, e:
                log.debug( "_terminate_process( %i ): %s", pid, e )

        if retpid == pid:
            if os.WIFEXITED(status):
                rc = os.WEXITSTATUS(status)
            elif os.WIFSIGNALED(status):
                sig = os.WTERMSIG(status)
        else:
            self._kill_process(pid)

    def kill_all_processes(self):
        for pid in self.processes:
            try:
                self._kill_process(pid)   
            except OSError, e:
                log.debug ("couldn't kill process: %s", e)

        self.processes = []

    def _kill_process(self, pid):
       os.kill(pid,signal.SIGKILL)
       maxWaits = 5
       waitTime = 1
       elapsedWaits = 0
       retpid = 0
       try:
           while elapsedWaits < maxWaits:
               (retpid,status) = os.waitpid(pid, os.WNOHANG )
               if retpid == pid and os.WIFSIGNALED(status):
                   break
               time.sleep(waitTime)
               elapsedWaits += 1
       except OSError, e:
           log.debug ( "_kill_process, waitpid %i : %s", pid, e )
       if retpid == pid:
           if os.WIFEXITED(status):
               rc = os.WEXITSTATUS(status)
           elif os.WIFSIGNALED(status):
               sig = os.WTERMSIG(status)
       else:
           log.debug("_kill_process, process %i not killed or waitpid() failed.", pid)


if __name__ == "__main__":
    mgr = ProcessManager()
    mgr.start_process("date",[])

    time.sleep(3)

    mgr.terminate_all_processes()

    
