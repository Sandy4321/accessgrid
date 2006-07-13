#-----------------------------------------------------------------------------
# Name:        RssReader.py
# Purpose:     An RSS reader for meeting feeds
# Created:     2005/10/19
# RCS-ID:      $Id: RssReader.py,v 1.8 2006-07-13 15:03:56 turam Exp $
# Copyright:   (c) 2005
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
"""
RssReader combines an RSS parser, feed url management, and timed updates,
with the option of adding observers to get notification of changes
"""


import threading
import calendar

import socket
Timeout = socket.getdefaulttimeout()
import feedparser

# work around apparent bug in socket.setdefaulttimeout,
# which is used in feedparser
socket.setdefaulttimeout(Timeout)

def strtimeToSecs(strtime):
    """
    Convert a time string to seconds since the epoch
    
    The time string is assumed to be in the form:
    
    "01 Sep 2005 hh:mm:ss TZ"
    
    following rules for time specs laid out in RFC 822
    """
    
    MonthIndex = {'Jan':1, 'Feb':2, 'Mar':3, 'Apr':4, 'May':5, 'Jun':6,
                  'Jul':7, 'Aug':8, 'Sep':9, 'Oct':10,'Nov':11,'Dec':12 }
    parts = strtime.split()
    if len(parts) != 5:
        raise Exception("Invalid string time input")
        
    day = int(parts[0])
    mon_str = parts[1]
    mon = MonthIndex[mon_str]
    year = int(parts[2])
    
    time_str = parts[3]
    time_parts = time_str.split(':')
    hour = int(time_parts[0])
    min = int(time_parts[1])
    sec = 0
    if len(time_parts) > 2:
        sec = int(time_parts[2])
        
    time_tuple = (year,mon,day,hour,min,sec,-1,-1,-1)
    
    time_secs = calendar.timegm(time_tuple)
    
    return time_secs


class RssReader:
    """
    RssReader takes a list of RSS urls which it should watch,
    updating when the specified duration has expired.
    
    RssReader accepts registration of observers, which will be updated
    with calls to the following methods:
    
        Update
        Error
        
    """
    def __init__(self,rssUrlList,updateDuration=1800,observers=[],log=None):
        self.rssUrlList = rssUrlList
        self.updateDuration = updateDuration 
        self.observers = observers
        self.log = log
                
        self.entries = {}
        
        self._StartTimer()
        
    def Synch(self):
        for rssUrl in self.rssUrlList:
            self._ProcessUrl(rssUrl)
        
    def _ProcessUrl(self,rssUrl):
        
        if self.log: 
            self.log.debug('Retrieving rss: %s', rssUrl)

        d = feedparser.parse(rssUrl)
        channelTime = d['feed']['modified']
        docDate = strtimeToSecs(channelTime)
    
        store = 0
        if rssUrl in self.entries.keys():
            lastDocDate = self.entries[rssUrl][1]
            if lastDocDate < docDate:
                # document has been updated; store it
                store = 1
        else:
            # new document; store it
            store = 1

        if store:  
    
            if self.log: self.log.debug('Storing rss: %s', rssUrl)
    
            self.entries[rssUrl] = (d,docDate)
            
            # Update observers
            map(lambda o: o.UpdateRss(rssUrl,d,docDate),self.observers)

    
    def SetUpdateDuration(self,updateDuration):
    
        wereEqual = (self.updateDuration == updateDuration)
    
        self.updateDuration = updateDuration
        
        if not wereEqual:
            self._RestartTimer()
        
    def _RestartTimer(self):
        self.timer.cancel()
        self._StartTimer()
        
    def _StartTimer(self):
        if self.updateDuration > 0:
            self.timer = threading.Timer(self.updateDuration,self._TimedUpdate)
            self.timer.start()
            
    def _TimedUpdate(self):
        try:
            self.Synch()
        except Exception,e:
            print 'exception updating feed:', e
        if self.updateDuration > 0:
            self.timer = threading.Timer(self.updateDuration,self._TimedUpdate)
            self.timer.start()
    
    def AddObserver(self,observer):
        self.observers.append(observer)
        
    def RemoveObserver(self,observer):
        self.observers.remove(observer)
        
    def AddFeed(self,url):
        self._ProcessUrl(url)
        
    def GetFeeds(self):
        return self.entries.keys()
        
    def RemoveFeed(self,url):
        if url in self.entries.keys():
            del self.entries[url]
        else:
            print 'url not found', url
    
class ReaderObserver:
    def UpdateRss(self,url,d,date):
        print 'got update:', url,d,date
        
    def Error(self,err):
        print 'got error:', err


if __name__ == '__main__':
    updateDuration = 10          
    rssUrlList = ['http://www.mcs.anl.gov/~turam/rss.cgi',
                  'http://www.mcs.anl.gov/~turam/agschedule.xml']

    observers = [ReaderObserver()]
    reader = RssReader(rssUrlList,updateDuration,observers)

