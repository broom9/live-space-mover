#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
This script copies entries from a live space (msn space) weblog to an other weblog, using the MetaWeblog API.
It can move posts now, not supporting comments yet.
Require 'BeautifulSoup' module
Released under the GPL. Report bugs to weiwei9@gmail.com

(c) Wei Wei, homepage: http://www.broom9.com
General Public License: http://www.gnu.org/copyleft/gpl.html
"""

__VERSION__="0.2"

import sys
import xmlrpclib
import urllib2
from BeautifulSoup import BeautifulSoup
import re
import logging
from datetime import datetime
import time
from optparse import OptionParser

logging.basicConfig(level=10);

    
def fetchEntry(url,datetimePattern = '%m/%d/%Y %I:%M %p'):
    logging.debug("begin fetch page %s",url)
    page = urllib2.urlopen(url)
    soup = BeautifulSoup(page)
    logging.debug("fetch page successfully")
    #logging.debug(soup.prettify())
    i={}
    #date
    temp = soup.find(id=re.compile('LastMDatecns[!0-9]+'))
    if temp :
        i['date']=temp.string.strip()
        logging.debug("found date %s",i['date'])
    else :
        print "Can't find date"
        sys.exit(2)
    #time
    temp = soup.find(attrs={"class":"footer"})
    if temp :
        timeStr = temp.span.string.strip()
        i['date']+= (' '+timeStr)
        i['date'] = datetime.strptime(i['date'],datetimePattern)
        logging.debug("found time %s",i['date'])
    else :
        print "Can't find time or can't parse datetime"
        sys.exit(2)
    #title
    temp = soup.find(id=re.compile('subjcns[!0-9]+'))
    if temp :
        i['title']=temp.string.strip()
        logging.debug("found title %s",i['title'])
    #content
    temp = soup.find(id=re.compile('msgcns[!0-9]+'))
    if temp :
        i['content']=''.join(map(str,temp.contents))
        logging.debug("found content");
    #previous entry link
    temp = soup.find(id='ctl00_MainContentPlaceholder_ctl00_Toolbar_Internal_LeftToolbarList');
    if temp and temp.li :
        i['permalLink'] = temp.li.a['href']
        logging.debug("found previous permalink %s",i['permalLink'])
    #comments
    temp = soup.findAll(attrs={"class":"bvCommentText bvwordwrap"})
    if temp :
        i.comments = []
        for cmDiv in temp:
            comment = {}
            comment['author']=cmDiv.contents[0]
            comment['content']=''.join(map(str,cmDiv.contents[1]))
            comment['date']=datetime.strptime(cmDiv.contents[2],datetimePattern)
            
            i.comments.append(comment)
    return i

def publish(server, blogid, user, passw, wpost,published):
    good=False
    i = 1
    while not good and i<6:
        try:
                logging.debug("publishing post on new weblog (account:%s); try:%d)...",user,i)
                server.metaWeblog.newPost(blogid,user,passw,wpost,published)
                good = True
        except:
                good = False
                logging.debug("error. Retrying...")
                time.sleep(3+i)
        i+=1
    if not good:
        server.metaWeblog.newPost(blogid, user, passw, wpost, published)


def find1stPermalink(srcURL):
    logging.info("connectiong to source blog %s",srcURL)
    page = urllib2.urlopen(srcURL)
    logging.info("connect successfully, look for 1st Permalink")
    soup = BeautifulSoup(page)
    textNode = soup.find(text=["Permalink",u"????"])
    if textNode :
        linkNode = textNode.parent
    else :
        logging.debug("trying a not so solid method");
        linkNode = soup.find(attrs={"class":"footer"}).findAll('a')[3]
    if linkNode :
        logging.info("Found 1st Permalink %s",linkNode["href"])
        return linkNode["href"];
    else :
        logging.error("Can't find 1st Permalink")
        return False
    
def tryPost(postURL = 'http://blog.broom9.com/my-wp-comments-post.php'):
    logging.info('Try to post a comment')
    data = urllib.urlencode({"comment_post_ID":"562",\
        'author':'tessster','email':'tessstemail@test.com','url':'http://tesssturl.com',\
        'comment':'tesasdfastcontent','date':'2005-1-1 17:02'})
    f = urllib.urlopen(postURL,data)
    s = f.read()
    if s=='Success' : logging.debug('Post comment successfully')
    else : logging.debug('Post comment failed')
    f.close()
 
def main():
    #main procedure begin
    parser = OptionParser()
    parser.add_option("-s","--source",action="store", type="string",dest="srcURL",default="http://yourspaceid.spaces.live.com/",help="source msn/live space address")
    parser.add_option("-f","--startfrom",action="store", type="string",dest="startfromURL",help="a permalink in source msn/live space address for starting with, if this is specified, srcURL will be ignored.")    
    parser.add_option("-d","--dest",action="store",type="string",dest="destURL",default="http://your.wordpress.blog.com/xmlrpc.php",help="destination wordpress blog address (must point to xmlrpc.php)")
    parser.add_option("-u","--user",action="store",type="string",dest="user",default="yourusername",help="username for logging into destination wordpress blog")
    parser.add_option("-p","--password",action="store",type="string",dest="passw",default="yourpassword",help="password for logging into destination wordpress blog")
    parser.add_option("-x","--proxy",action="store",type="string",dest="proxy",help="http proxy server, only for connecting live space.I don't know how to add proxy for metaWeblog yet. So this option is probably not useful...")
    parser.add_option("-t","--datetimepattern",action="store",dest="datetimepattern",default="%m/%d/%Y %I:%M %p",help="The datetime pattern of livespace, default to be %m/%d/%Y %I:%M %p. Check http://docs.python.org/lib/module-time.html for time formatting codes. Make sure to quote the value in command line.")
    parser.add_option("-b","--draft",action="store_false",dest="draft",default=True,help="as published posts or drafts after transfering,default to be published directly")
    parser.add_option("-l","--limit",action="store",type="int",dest="limit",help="limit number of transfered posts, you can use this option to test")
    (options, args) = parser.parse_args()
    #export all options variables
    for i in dir(options):
        exec i+" = options."+i
    #add proxy
    if proxy:
        proxy_handler = urllib2.ProxyHandler({'http': proxy})
        opener = urllib2.build_opener(proxy_handler)
        urllib2.install_opener(opener)
        logging.debug("setting proxy to %s",proxy)
    #test username/password and desturl valid
    server=xmlrpclib.Server(destURL)
    blogid = int(1)
    try:
        server.metaWeblog.getUsersBlogs(blogid,user,passw)
    except xmlrpclib.ProtocolError,xmlrpclib.ResponseError:
        print "Error while checking username",user,". Possible reasons are:"
        print " - The weblog doesn't exist"
        print " - Path to xmlrpc server is incorrect"
        print "Check for typos."
        sys.exit(2)
    except xmlrpclib.Fault:
        print "Error while checking username",user,". Possible reasons are:"
        print " - your weblog doesn't support the MetaWeblog API"
        print " - your weblog doesn't like the username/password combination you've provided."
        sys.exit(2)
    #connect src blog and find first permal link
    if startfromURL :
    	permalink = startfromURL
    else :
    	permalink = find1stPermalink(srcURL)
    #main loop, retrieve every blog entry and post to dest blog
    count = 0
    while permalink:
        i=fetchEntry(permalink,datetimepattern)
        if 'title' in i:
            logging.info("Got a blog entry titled %s successfully",i['title'])
        wpost = {}
        wpost['description']=i['content']
        wpost['title'] = i['title']
        wpost['dateCreated']=i['date']
        publish(server,blogid,user,passw,wpost,draft)
        logging.info("Published the blog entry successfully")
        logging.info("-----------------------")
        if 'permalLink' in i :
        	permalink = i['permalLink']
        else :
        	break
        count+=1
        if limit and count >= limit : break
    print "Finished! Congratulations!"

if __name__=="__main__":
    main()

