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
import urllib2,urllib,codecs
from collections import defaultdict
from pygooglechart import Chart, SimpleLineChart, GroupedVerticalBarChart, Axis
from Cheetah.Template import Template

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
                """Theoretically returns the longest common substring
                between its arguments. Actually implemented with very
                string assumptions."""
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
                "Returns a dict of word cound data for each commit hash in revs."
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
                "Returns the datetime corresponding to a given commit hash."
                commitdate = getpipeoutput(['git show --pretty=format:%at {0}'.format(rev),
                                            'head -n 1']).rstrip('\n')
                return datetime.datetime.fromtimestamp(float(commitdate))

        def collect(self,dir):
                """Returns history, revdata, revdates, where history is
                the sequence of commits that occured to the selected
                branch, and revdata, revdates are runs of collectrevdata
                and retrievedate on them, respectively. Maintains and uses
                a cache file to that effect.
                """
                DataCollector.collect(self,dir)
                self.loadCache('cachefile')

                subprocess.check_call(['git','checkout',conf['initbranch']])
                # do I have to update anything ?
                try:
                        knownlatest = self.cache['latest']
                        latesthash = getpipeoutput(['git rev-list %s -n 1'
                                                    % conf['initbranch']])
                        latest = self.retrievedate(latesthash)
                        if latest == knownlatest:
                                return (self.cache['revs'],
                                        self.cache['revdata'],
                                        self.cache['revdates'])
                except KeyError:
                        pass

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
                self.cache['latest'] = revdates[history[0]]
                self.saveCache('cachefile')

                # Cleanup
                subprocess.check_call(['git','checkout',initbranch])
                subprocess.check_call(['git','branch','-D', self.projectname])

                return history, revdata, revdates

        def getcalendar(self,history,revdata,revdates):
                # at this stage, history was antechronological,
                history.reverse()
                wordsperday = map(lambda x: (datetime.date.fromordinal(revdates[x].toordinal()),
                                        revdata[x]),
                                  history)
                firstdate = wordsperday[0][0]
                # this strongly depende on history having been chronological
                old = datetime.date.today()-firstdate

                vals = defaultdict(int)
                incrs = defaultdict(int)
                for date,data in wordsperday:
                        # later (= higher, supposedly) override earlier in the same day
                        vals[date] = data

                # Pad null vals with vals from previous days
                # fill out increments
                latestval = wordsperday[0][1]
                for i in range(0, old.days):
                        date = datetime.date.today() + datetime.timedelta(-old.days + i)
                        if vals[date] == 0:
                                vals[date] = latestval
                                incrs[date] = 0
                        else:
                                latestval = vals[date]
                                if date != firstdate:
                                        yesterday = (date-datetime.timedelta(1))
                                        incrs[date] = vals[date]-vals[yesterday]

                return old.days,vals,incrs

        def linegraph(self,days,bars,output,title = ""):
                data = []
                min_count = 0
                max_count = 0
                date = lambda i:datetime.date.today() + datetime.timedelta(-days + i)

                for i in range(0,days):
                        count = bars[date(i)]
                        max_count = max(count,max_count)
                        min_count = min(count,min_count)
                        data.append(count)
                chart = SimpleLineChart(800,350,y_range=[min_count, 60000])
                chart.add_data(data)
                # Set the line colour to blue
                chart.set_colours(['0000FF'])

                # Set the vertical stripes
                d = max(1/float(days),round(7/float(days),2))
                chart.fill_linear_stripes(Chart.CHART, 0, 'CCCCCC', d, 'FFFFFF', d)

                fmt="%d/%m"
                chart.set_axis_labels(Axis.BOTTOM, \
                                      [date(i).strftime(fmt) for i in range(0,days,7)])

                # Set the horizontal dotted lines
                chart.set_grid(0, 25, 5, 5)

                # The Y axis labels contains 0 to 100 skipping every 25, but remove the
                # first number because it's obvious and gets in the way of the first X
                # label.
                delta = float(max_count-min_count) / 100
                skip = int(delta) / 5 * 100
                left_axis = range(0, 60000 + 1, skip)
                left_axis[0] = ''
                chart.set_axis_labels(Axis.LEFT, left_axis)

                if len(title) > 0:
                        chart.set_title(title % days)

                chart.download(output)

        def bargraph(self,days,bars,output,title = ""):

                data = []
                min_count = 0
                max_count = 0
                date = lambda i:datetime.date.today() + datetime.timedelta(-days + i)

                for i in range(0,days):
                        count = bars[date(i)]
                        max_count = max(count,max_count)
                        min_count = min(count,min_count)
                        data.append(count)
                chart = GroupedVerticalBarChart(800,300,y_range=[min_count, max_count])
                chart.add_data(data)
                chart.set_bar_width(500 / days)
                # Set the line colour to blue
                chart.set_colours(['0000FF'])

                # Set the horizontal dotted lines
                chart.set_grid(0, 25, 5, 5)

                if days >= 30:
                        fmt = "%d"
                else:
                        fmt="%d/%m"
                chart.set_axis_labels(Axis.BOTTOM, \
                                      [date(i).strftime(fmt) for i in range(0,days)])

                # The Y axis labels contains 0 to 100 skipping every 25, but remove the
                # first number because it's obvious and gets in the way of the first X
                # label.
                delta = float(max_count-min_count) / 100
                skip = max(int(delta) / 5 * 100,100)
                left_axis = range(0, max_count + 1, skip)
                left_axis[0] = ''
                chart.set_axis_labels(Axis.LEFT, left_axis)

                if len(title) > 0:
                        chart.set_title(title % days)

                chart.download(output)

        def wordsperdayavg(self,days,bars):
                date = lambda i:datetime.date.today() + datetime.timedelta(-days + i)
                vals = [bars[date(i)] for i in range(0,days)]
                average = reduce(lambda x,y :x+y,vals,0) / len(vals)
                return average

        def wpdgraph(self,val,output, title = ""):
                width = 500
                height = 250
                adjectives = ['lazy','decent','productive','good','fantastic']
                adjective = adjectives[min(int(val/400),len(adjectives)-1)]
                labels = '0:|'+adjective+'|1:|slow|faster|Stephen_King'
                url='http://chart.apis.google.com/chart?cht=gom&chco=FF0000,00FF00&chxt=x,y&chd=t:%s&chs=%sx%s&chxl=%s&chtt=%s'
                url = url % (float(val)/20,width,height,labels,urllib.quote(title))

                opener = urllib2.urlopen(url)
                if opener.headers['content-type'] != 'image/png':
                        raise BadContentTypeException('Server responded with a ' \
                                                      'content-type of %s' % opener.headers['content-type'])
                open(output, 'wb').write(opener.read())

g = GitDataCollector()
revs, data, dates = g.collect('doc/manuscrit-francois')
old, cal, incrs = g.getcalendar(revs, data, dates)
outdir = os.path.expanduser('~/tmp/git-wordcount')
g.linegraph(30,cal,os.path.join(outdir,'adv.png'),title="Total number of words (last %s days)")
g.bargraph(30,incrs,os.path.join(outdir,'incr.png'),title="Words written per day (last %s days)")
proddays = 7
while g.wordsperdayavg(proddays,incrs) == 0:
        proddays = proddays+1

ttl = "Productivity (last %s days)" % proddays
tmpldir = os.path.expanduser('~/tmp/git-wordcount')

total = cal[datetime.date.today()+datetime.timedelta(-1)]
print "DEBUG total",total
avg = g.wordsperdayavg(proddays,incrs)

g.wpdgraph(avg,os.path.join(outdir,'wpd.png'),title=ttl)

remainingwords = (60000 - total)
remainingdays = remainingwords / avg
remainingskdays = remainingwords / 2000
enddate = datetime.date.today() + datetime.timedelta(remainingdays)
endskdate = datetime.date.today() + datetime.timedelta(remainingskdays)
datefmt = "%A, %B %d, %Y"

t = Template(
    file=os.path.join(tmpldir,"dashboard.tmpl"),
    searchList = {
                'total' : total,
                'days' : proddays,
                'wpd' : avg,
                'enddate' : enddate.strftime(datefmt),
                'skenddate' : endskdate.strftime(datefmt),
    }
)
out = codecs.open(os.path.join(outdir,"index.html"), mode="w", encoding='utf-8')
out.write(unicode(t))
out.close()
