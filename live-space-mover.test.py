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
import os
import xmlrpclib
import urllib
import urllib2
from BeautifulSoup import BeautifulSoup,Tag
import re
import logging
from datetime import datetime
import time
from optparse import OptionParser
from string import Template
import pickle
import xml



    
def fetchEntry(url,datetimePattern = '%m/%d/%Y %I:%M %p',mode='all'):
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
    i['comments'] = []
    if mode != 'postsOnly' :
        needFetchComments = True
        ajaxNextPageFlag = False
    
        #maybe need to fetch several pages of comments
        while needFetchComments:
            temp = soup.findAll(attrs={"class":"bvCommentText bvwordwrap"})  #a comment div
            if temp :
                for cmDiv in temp:
                    comment = {}
                    #the name and email element. The first page is different from latter pages, latter ones have a "span" element more
                    mailAndName = cmDiv.contents[0]
                    if isinstance(mailAndName,Tag) and mailAndName.name == 'span' :
                        mailAndName = mailAndName.contents[0]
                    if isinstance(mailAndName,Tag):
                        comment['email']=mailAndName['href'][8:]
                        comment['author']=mailAndName.string
                    else:
                        comment['author']= mailAndName
                    comment['comment']=''.join(map(str,cmDiv.contents[1]))
                    comment['date']=datetime.strptime(cmDiv.contents[2],datetimePattern).strftime("%Y-%m-%d %H:%M")
                    urlTag = cmDiv.contents[2].findNextSibling(name='a')
                    if urlTag:
                        comment['url']=urlTag['href']
                    i['comments'].append(comment)
            #fetch next page comments
            #for first page, find this link
            #for ajaxStr, look at ajaxNextPageFlag, that depends on a parameter returned in ajaxStr
            nextPageCommentATag = soup.find(attrs={"title":"Click to view next 20 comments"})
            if nextPageCommentATag or ajaxNextPageFlag:
                needFetchComments = True
                #Make ajax request URL
                t = Template('http://${domainname}/parts/blog/script/BlogService.fpp?cn=Microsoft.Spaces.Web.Parts.BlogPart.FireAnt.BlogService'
                             +'&mn=get_comments&d=${entryid},${commentid},1,20,Public,0,Journey,2007%2F6%2F19%207%3A30%3A22en-US2007-06-06_11.36&v=0&ptid=&a=')
                domainname = re.compile(r'http://[\w.]+/blog').findall(url)[0][len('http://'):-len('/blog')]
                entryid = re.compile(r'cns![\w!.]+entry').findall(url)[0][:-len('.entry')]
                if nextPageCommentATag:
                    commentid = re.compile(r'commentPH=cns![\w!.]+&').findall(nextPageCommentATag['href'])[0][len('commentPH='):-len('&')]
                elif ajaxStr:
                    commentid= ajaxStr.rsplit(',',6)[1][1:-1]
                ajaxURL = t.substitute(domainname = domainname,entryid = entryid, commentid = commentid)
                logging.debug(ajaxURL)
                ajaxStr = urllib2.urlopen(ajaxURL).read()
                
                #set ajaxNextPageFlag
                
                ajaxNextPageFlag = ajaxStr.rsplit(',',4)[1][:-2] == 'true'
                
                #Parse ajax result
                ajaxStrWOScripts = re.findall(r'"<ul>.*</ul>"',ajaxStr)
                if ajaxStrWOScripts:
                    newHTML = ajaxStrWOScripts[0]
                    newHTML = newHTML.replace('\\','')
                    soup = BeautifulSoup(newHTML)
                else :
                    logging.error('Error when parsing ajax result ')
                    logging.error(ajaxStr)
            else :
                needFetchComments = False
        logging.debug('Got %d comments of this entry'
                  ,len(i['comments']))
    return i
    
def getDstBlogEntryList(server, user, passw, maxPostID = 100):
    logging.info('Fetching dst blog entry list')
    pIdRange = range(1,maxPostID)
    entryDict = {}
    successCount = 0
    errorCount = 0
    for pId in pIdRange:
        try:
            entry = server.metaWeblog.getPost(pId,user,passw)
            entryDict[entry['title']]=pId
            logging.debug("Get post %s, title is %s",pId,entry['title'])
            successCount+=1
        except xmlrpclib.Fault:
            logging.debug("No post of id %s", pId)
        except xml.parsers.expat.ExpatError:
            logging.warn("Failed to retrieve Post with id %d",pId)
            errorCount+=1
    logging.info('Get %d posts successfully. %d posts failed. Check warning log to see details',successCount,errorCount)
    return entryDict
    
def publishPost(server, blogid, user, passw, wpost,published):
    i = 1
    while i<6:
        try:
            logging.debug("publishing post on new weblog (account:%s); try:%d)...",user,i)
            return server.metaWeblog.newPost(blogid,user,passw,wpost,published)
        except:
            logging.debug("error. Retrying...")
            time.sleep(3+i)
            i+=1

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
    
def publishComments(entry,postCommentsURL,pID=0,dstBlogEntryDict={}):
    if len(entry['comments'])>0 :
        logging.debug('Try to publish comments for post %s',entry['title'])
        if not pID:
            if dstBlogEntryDict.has_key(entry['title']):
                pID = dstBlogEntryDict[entry['title']]
            else:
                logging.warn("No pID provided, and can't find this post title in dest blog entries dict")
                return
        for c in entry['comments']:
            c["comment_post_ID"]=pID
            data = urllib.urlencode(c)
            f = urllib.urlopen(postCommentsURL,data)
            s = f.read()
            if s=='Success' : logging.debug('Post comment successfully')
            else : logging.debug('Post comment failed')
            f.close()
          
def tryPost(postURL = 'http://blog.broom9.com/my-wp-comments-post.php'):
    logging.info('Try to post a comment')
    data = urllib.urlencode({"comment_post_ID":"562",\
        'author':'tessster','email':'tessstemail@msn.com','url':'http://tesssturl.com',\
        'comment':'tesasdfasasdfatcontent','date':'2005-1-1 17:02'})
    f = urllib.urlopen(postURL,data)
    s = f.read()
    print s
    if s.endswith('Success') : logging.debug('Post comment successfully')
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
    parser.add_option("-m","--mode",action="store",type="string",dest="mode",default="all",help="Working mode, 'all' or 'commentsOnly'. Default is 'all'. Set it to 'commentsOnly' if you have used earlier version of this script to move posts. Set it to 'postsOnly' if you can't upload the comments-post page to your dest WordPress blog so can't move comments")
    parser.add_option("-c","--postcommentsurl",action="store",type="string",default='',dest="postCommentsURL",help="The URL for posting comments, usually should be the URL of 'my-wp-comments-post.php' provided with this script. If this option isn't set, program will use destURL and the default page name to decide.")    
    (options, args) = parser.parse_args()
    #export all options variables
    for i in dir(options):
        exec i+" = options."+i
    #decide postCommentsURL
    if len(postCommentsURL)==0:
        postCommentsURL = destURL.rsplit('/',1)[0]+'/my-wp-comments-post.php'
        logging.info('Set postCommentsURL to %s', postCommentsURL)
    #add proxy
    if proxy:
        proxy_handler = urllib2.ProxyHandler({'http': proxy})
        opener = urllib2.build_opener(proxy_handler)
        urllib2.install_opener(opener)
        logging.info("Set proxy to %s",proxy)
    #test username/password and desturl valid
    server=xmlrpclib.ServerProxy(destURL,verbose = 0)
    blogid = int(1)
    try:
        server.metaWeblog.getUsersBlogs(blogid,user,passw)
        logging.info('Connect to dest blog successfully')
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
    #Load or Fetch dst blog entries dict (title and id)
    if mode == 'commentsOnly':
        logging.info('Comments Only mode, try to get a dict of dest blog entries')
        loadedDump = False
        if os.path.exists('DstEntryDict.dump') :
            try :
                f = open('DstEntryDict.dump')
                dstBlogEntryDict = pickle.load(f)
                f.close()
                loadedDump = True
                logging.info('Finished Loading Destination Blog Entries from local cache')
            except Exception:
                logging.info('Loading DstEntryDict.dump failed, begin to fetch')
                loadedDump = False
        if not loadedDump :
            f = open('DstEntryDict.dump','w')
            dstBlogEntryDict = getDstBlogEntryList(server,user,passw,580)
            pickle.dump(dstBlogEntryDict,f)
            f.close()
            logging.info('Finished Fetching Destination Blog Entries from site, and saved to local for caching')
    #connect src blog and find first permal link
    if startfromURL :
            permalink = startfromURL
    else :
            permalink = find1stPermalink(srcURL)
    #main loop, retrieve every blog entry and post to dest blog
    count = 0
    while permalink:
        i=fetchEntry(permalink,datetimepattern,mode)
        if 'title' in i:
            logging.info("Got a blog entry titled %s successfully",i['title'])
        
        wpost = {}
        wpost['description']=i['content']
        wpost['title'] = i['title']
        wpost['dateCreated']=i['date']
        if mode == 'all':
            pID = publishPost(server,blogid,user,passw,wpost,draft)
            publishComments(entry=i,pID=pID,postCommentsURL=postCommentsURL)
        elif mode == 'postsOnly':
            publishPost(server,blogid,user,passw,wpost,draft)
        else : #mode='commentsOnly'
            publishComments(entry=i,dstBlogEntryDict=dstBlogEntryDict,postCommentsURL=postCommentsURL)
        logging.info("-----------------------")
        if 'permalLink' in i :
                permalink = i['permalLink']
        else :
                break
        count+=1
        if limit and count >= limit : break
    print "Finished! Congratulations!"

if __name__=="__main__":
    #print fetchEntry('http://broom9.spaces.live.com/blog/cns!3EB2F0E9A1AE7429!464.entry')
    logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='live-space-mover.log',
                    filemode='w');
    # define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    # set a format which is simpler for console use
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)
    #tryPost()
    main()
    
    

