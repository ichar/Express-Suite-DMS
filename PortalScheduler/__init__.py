"""
Portal Scheduler Tool
$Id: __init__.py, v 1.0 2008/02/20 12:00:00 Exp $

*** Checked 20/02/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import ZODB
import threading

import Config
import Scheduler
import SchedulersList

ZOPE_IS_OLD = 0

from logging import getLogger
logger = getLogger( '%s.PortalScheduler' % Config.ProductName )

_started = 0
_threads = []

def startThreads( *args ):
    while _threads:
        t = _threads.pop(0)
        try:
            if t.getName().find('PortalScheduler') == 0 and not t.isAlive():
                t.start()
        except:
            pass
    _started = 1

def asyncore_loop( timeout=30.0, use_poll=0, map=None ):
    startThreads()
    asyncore.loop = asyncore._app_loop
    del asyncore._app_loop
    asyncore.loop( timeout, use_poll, map )

if not _started and Config.AutoStartDaemonThreads and ZOPE_IS_OLD:
    try:
        from ThreadedAsync import register_loop_callback
        logger.info( 'Registering callback' )
        register_loop_callback( startThreads )

    except ImportError:
        from ZServer import asyncore
        if not hasattr( asyncore, '_app_loop' ):
            logger.info( 'Patching asyncore' )
            asyncore._app_loop = asyncore.loop
            asyncore.loop = asyncore_loop

def initialize( context ):
    for module in [
                    Scheduler,
                    SchedulersList,
                  ]:
        module.initialize( context )

    product = context._ProductContext__prod
    Config.ProductName = product.id
    Config.ProductVersion = product.version.split()[-1]

    ScheduleElement.initialize( context )

    if _started:
        return

    app = context._ProductContext__app
    schedulers_list = getattr( app, 'SchedulersList', None )
    if schedulers_list:
        for scheduler in schedulers_list.listSchedulers():
            _threads.append( scheduler.startDaemon( postpone=1 ) )

    if not _started and Config.AutoStartDaemonThreads and not ZOPE_IS_OLD:
        #its safe to start threads here because their run() method waits for Zope startup.
        startThreads()
