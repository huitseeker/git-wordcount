#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Script to count words after each commit
@author: François
@organization: INRIA
"""
__version__='$Id$'

import datetime
#import getopt
#import glob
import os
import pickle
import platform
# import re
# import shutil
import subprocess
import sys
import time
import zlib

GNUPLOT_COMMON = 'set terminal png transparent\nset size 1.0,0.5\n'
ON_LINUX = (platform.system() == 'Linux')
WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')

exectime_internal = 0.0
exectime_external = 0.0
time_start = time.time()

# By default, gnuplot is searched from path, but can be overridden with the
# environment variable "GNUPLOT"
gnuplot_cmd = 'gnuplot'
if 'GNUPLOT' in os.environ:
        gnuplot_cmd = os.environ['GNUPLOT']

conf = {
        'max_domains': 10,
        'max_ext_length': 10,
        'style': 'gitstats.css',
        'max_authors': 20,
        'authors_top': 5,
        'commit_end': '',
        'linear_linestats': 1,
        'dir' : 'doc/manuscrit-francois',
        'initbranch' : 'manuscript',
        'adversebranch' : 'manuscript',
#        'commit_begin' : '2e7b05e644b9893aa5a509963e33bd98ba3ba6b7',
#        'commit_begin' : '512ede70596053900ad247414b4bb7794f097f00'
        'commit_begin' : '',
        'authorpattern': 'garillot',
}

def getpipeoutput(cmds, quiet = True):
        global exectime_external
        start = time.time()
        if not quiet and ON_LINUX and os.isatty(1):
                print '>> ' + ' | '.join(cmds),
                sys.stdout.flush()
        p0 = subprocess.Popen(cmds[0], stdout = subprocess.PIPE, shell = True)
        p = p0
        for x in cmds[1:]:
                p = subprocess.Popen(x, stdin = p0.stdout,
                                     stdout = subprocess.PIPE,
                                     shell = True)
                p0 = p
        output = p.communicate()[0]
        end = time.time()
        if not quiet:
                if ON_LINUX and os.isatty(1):
                        print '\r',
                print '[%.5f] >> %s' % (end - start, ' | '.join(cmds))
        exectime_external += (end - start)
        return output.rstrip('\n')

def getoutput(cmd, quiet = True):
        global exectime_external
        start = time.time()
        if not quiet and ON_LINUX and os.isatty(1):
                print '>> ' + cmd,
                sys.stdout.flush()
        p0 = subprocess.Popen(cmd, stdout = subprocess.PIPE, shell = True)
        p = p0
        output = p.communicate()[0]
        end = time.time()
        if not quiet:
                if ON_LINUX and os.isatty(1):
                        print '\r',
                print '[%.5f] >> %s' % (end - start, cmd)
        exectime_external += (end - start)
        return output.rstrip('\n')

def getcommitrange(defaultrange = 'HEAD', end_only = False):
        if len(conf['commit_end']) > 0:
                if end_only or len(conf['commit_begin']) == 0:
                        return conf['commit_end']
                return '%s..%s' % (conf['commit_begin'], conf['commit_end'])
        return defaultrange

def getkeyssortedbyvalues(dict):
        return map(lambda el : el[1], sorted(map(lambda el : (el[1], el[0]), dict.items())))

# dict['author'] = { 'commits': 512 } - ...key(dict, 'commits')
def getkeyssortedbyvaluekey(d, key):
        return map(lambda el : el[1], sorted(map(lambda el : (d[el][key], el), d.keys())))

VERSION = 0
def getversion():
        global VERSION
        if VERSION == 0:
                VERSION = getpipeoutput(["git rev-parse --short %s" % getcommitrange('HEAD')]).split('\n')[0]
        return VERSION

class DataCollector:
        """Manages data collection from a revision control repository."""
        def __init__(self):
                self.stamp_created = time.time()
                self.cache = {}

        ##
        # This should be the main function to extract data from the repository.
        def collect(self, dir):
                self.dir = dir
                self.projectname = os.path.basename(os.path.abspath(dir))

        ##
        # Load cacheable data
        def loadCache(self, cachefile):
                if not os.path.exists(cachefile):
                        return
                print >> sys.stderr, 'Loading cache...'
                f = open(cachefile, 'rb')
                try:
                        self.cache = pickle.loads(zlib.decompress(f.read()))
                except:
                        # temporary hack to upgrade non-compressed caches
                        f.seek(0)
                        self.cache = pickle.load(f)
                f.close()

        ##
        # Save cacheable data
        def saveCache(self, cachefile):
                print >> sys.stderr, 'Saving cache...'
                f = open(cachefile, 'wb')
                #pickle.dump(self.cache, f)
                data = zlib.compress(pickle.dumps(self.cache))
                f.write(data)
                f.close()

class GitDataCollector(DataCollector):

        def LCS(self,s1,s2):
                # ad-hoc incomplete lcs algo
                # we suspect a prefix of s2 (new history) is a suffix of s1 (old history)
                # aka s1 = t,u and s2 = u,v
                # so we start looking for s2 in s1
                for i in range(len(s1)):
                        if s1[i] == s2[0]:
                                # then there is the cursory verification that
                                # all following members of s1 match those of s2
                                if (len(s1) - i <=  len(s2)
                                # s2 is big enough to contain the suffix s1[i:]
                                    and reduce(lambda x, y : x and y,
                                             map(lambda e : e[0] == e[1],
                                                 [(s1[k+i],s2[k]) for k in range(1,len(s1) - i)])
                                             ,True)):
                                        # .. and s1[i:] is a prefix of s2
                                        return (i,0,len(s1) - i)
                                else:
                                        # there is junk at the end of s1, throw it away
                                        print "can't resolve substring match"
                                        return(0,0,0)
                # no match, we're in one of those rare cases where
                # s1 = u
                # s2 = t,u,v (aka some rewritten history)
                for i in range(len(s2)):
                        if s2[i] == s1[0]:
                                # we customarily verify the prefix is good
                                if (len(s1) <= len(s2) - i
                                    # s2[i:] is big enough to contain s1
                                    and reduce(lambda x, y : x and y,
                                             map(lambda e : e[0] == e[1],
                                                 [(s1[k],s2[k+i]) for k in range(1,len(s1))])
                                             ,True)):
                                        # and s1 is a prefix of s2[i:]
                                        return (0,i,len(s1))
                                else:
                                        # there is junk at the end of s1, throw it away
                                        print "can't resolve substring match"
                                        return (0,0,0)
                # we know that no prefix of s2 is in s1
                # and no prefix of s1 is in s2
                # hence no common substring, throw history away
                print "can't resolve substring match"
                return (0,0,0)

        def collectrevdata(self,revs):
                res = {}
                for rev in revs:
                        subprocess.check_call('git checkout %s' % rev,shell=True)
                        words = getpipeoutput(['wc -w *.src',
                                               'tail -n 1',
                                               "awk '{print $1}'"])
                        if not (len(words) == 0):
                                res[rev] = int(words)
                        else:
                                res[rev] = 0
                return res

        def retrievedate(self,rev):
                commitdate = getpipeoutput(['git show --pretty=format:%at {0}'.format(rev),
                                            'head -n 1']).rstrip('\n')
                return datetime.datetime.fromtimestamp(float(commitdate))

        def collect(self,dir):
                DataCollector.collect(self,dir)
                self.loadCache('cachefile')
                subprocess.check_call(['git','checkout',conf['initbranch']])
                # if dir was foo/bar at parent call,
                # creates a subtree branch reflecting `pwd`/foo/bar of initbranch, named bar
                created = getpipeoutput(['git branch','grep %s' % self.projectname])
                if len(created) == 0:
                        subprocess.check_call('git subtree split -P %s -b %s'
                                              % (dir,self.projectname),shell=True)
                # find the subtree's common ancestor with adversebranch
                # unless it's hardcoded in conf
                if len(conf['commit_begin']) == 0:
                        ancestor = getpipeoutput(['git rev-list --no-merges --reverse %s ^%s' % (self.projectname, conf['adversebranch']) ,
                                                  'head -n 1'])
                else:
                        ancestor = conf['commit_begin']
                # get all revisions from the split to the head of initbranch
                revs = getoutput('git rev-list --no-merges --author="%s" %s..%s'
                                 % (conf['authorpattern'],ancestor,self.projectname)).split('\n')
                revdata = {}
                revdates = {}

                # load previously met revs from the cache
                try:
                        knownrevs = self.cache['revs']
                        # I try to find the longest common substring (LCS) of revs
                        # between cached revs and revs
                        # - if knownrevs starts before revs, I have commited
                        #   (lost) some knownrevs to adversebranch, & will have to
                        #   get their data from cache
                        # - if revs starts before knownrevs, I have rewritten
                        #   history (!), chances are that I want to start
                        #   computing from revs
                        # - if there's junk at the beginning of both, this is just
                        #   too weird, abort
                        #   aka : (startknownr > 0 and startr > 0)
                        # - if knownrevs finish first, this is expected, I have
                        #   new commits
                        #   aka : (startr+length) < len(startr) - 1
                        # - if revs finish first, this is scary : I have rolled
                        #   back or lost data, abort
                        #   aka : (startknownr+length) < len(knownrevs) - 1
                        # - if there is "junk" at the end of both, I have
                        #   definitely rolled back, trust rev
                        (startknownr, startr, length) = self.LCS(knownrevs,revs)

                        if ((startknownr > 0 and startr > 0) or
                            (startknownr + length < len(knownrevs))):
                                print "I cannot reconcile history and this repo, aborting"
                                exit(1)

                        # henceforth knownrevs[startknownr:startknownr+length] is a suffix
                        if (startknownr > 0):
                                history = knownrevs[:startknownr-1]
                                toresolve = []

                        elif (startr > 0):
                                history = revs[:startr-1]
                                toresolve = revs[:startr-1]

                        else:
                                history = []
                                toresolve = []

                        history += revs[startr:startr+length]

                        if (startr+length) < len(revs):
                                history += revs[startr+length+1:]
                                toresolve += revs[startr+length+1:]

                        revdata.update(self.cache['revdata'])
                        revdates.update(self.cache['revdates'])

                # nothing in cache !
                except KeyError:
                        history = revs
                        toresolve = revs

                # the actual computation
                revdata.update(self.collectrevdata(toresolve))
                for rev in toresolve:
                        revdates[rev] = self.retrievedate(rev)

                # cache update
                self.cache['revs'] = history
                self.cache['revdata'] = revdata
                self.cache['revdates'] = revdates
                self.saveCache('cachefile')

                # history is reverse chronological
                history.reverse()
                # for rev in history:
                #         print revdates[rev].ctime()
                #         print revdata[rev]

                diffs = [(revdata[history[i]] - revdata[history[max(0,i-1)]])
                         for i in range(0,len(history))]
                for i in diffs:
                        print i




g = GitDataCollector()
g.collect('doc/manuscrit-francois')
