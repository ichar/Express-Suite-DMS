"""
Portal Scheduler. Scheduler class

*** Checked 31/03/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import Zope2

from Zope2.Startup import started as ZopeStarted
ZOPE_IS_OLD = 0

from mx.DateTime import now, DateTime

import string, re
from sys import exc_info
from types import ListType, TupleType

import threading
import transaction
import time
from whrandom import random

from AccessControl import ClassSecurityInfo
from Globals import InitializeClass, DTMLFile, Persistent
from OFS.ObjectManager import BadRequestException
from OFS.SimpleItem import SimpleItem

from ZODB.POSException import ConflictError, ReadConflictError

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import _getAuthenticatedUser

from Schedule import Schedule
from ScheduleElement import ScheduleElement

import Config
from Utils import cookId

from zLOG import INFO, ERROR
from Logger import LOG

from logging import getLogger
logger = getLogger( '%s.Scheduler' % Config.ProductName )

createSchedulerForm = DTMLFile('dtml/addPortalScheduler', globals())


def createScheduler( self, id='portal_scheduler', REQUEST={} ):
    """
        Adds Scheduler instance
    """
    ob = Scheduler( id )
    self._setObject( id, ob )

    if REQUEST is not None:
        return self.manage_main(self, REQUEST, update_menu=1)

def initialize( context ):
    context.registerClass(
        Scheduler,
        permission = 'Add Schedule',
        constructors = ( createSchedulerForm, createScheduler ), icon = 'www/Schedule.gif')

    context.registerHelpTitle( 'Scheduler Help' )
    context.registerHelp( directory='help' )

_dispatchers = {}


class Scheduler( SimpleItem ):
    """
        Scheduler 
    """
    meta_type = 'PortalScheduler'
    title = 'Scheduled Event Catalog'

    manage_options = (
            { 'label':'Daemon',       'action':'manageSchedulerForm'   },
            { 'label':'Events queue', 'action':'manageEventsQueueForm' },
            { 'label':'Schedule',     'action':'manageScheduleForm'    },
            { 'label':'Security',     'action':'manage_access'         },
            { 'label':'Undo',         'action':'manage_UndoForm'       },
        )

    security = ClassSecurityInfo()

    security.declareProtected(CMFCorePermissions.ManagePortal, 'manageSchedulerForm')
    manageSchedulerForm = DTMLFile('dtml/manageScheduler', globals())

    security.declareProtected(CMFCorePermissions.ManagePortal, 'manageScheduleForm')
    manageScheduleForm = DTMLFile('dtml/manageSchedule', globals())

    security.declareProtected(CMFCorePermissions.ManagePortal, 'manageEventsQueueForm')
    manageEventsQueueForm = DTMLFile('dtml/manageEventsQueue', globals())

    security.declareProtected(CMFCorePermissions.ManagePortal, 'manageTaskForm')
    manageTaskForm = DTMLFile('dtml/manageTask', globals())

    def __init__( self, id ):
        self.id = id
        self._schedule = Schedule()

    def _p_resolveConflict( self, o, s, n ):
        """
            Try to resolve conflict between container's objects
        """
        o['idx'] = max(o.get('idx') or 0, s.get('idx') or 0, n.get('idx') or 0)
        return o

    def _initstate( self, mode=None ):
        """
           Check the instance state (not established)
        """
        if mode or type(getattr(self._schedule, '_tree', None)) != type({}):
            schedule = Schedule()
            for id, ob in self._schedule.objectItems():
                schedule._setObject( id, ob )
            self._schedule = schedule
            self._p_changed = 1

            LOG('Scheduler._initstate', INFO, 'new schedule: %s' % len(schedule.keys()))
            return 1
        else:
            return None

    def __len__( self ):
        return self.getSize()

    def getSize( self ):
        return len(self._schedule.objectIds())

    security.declareProtected(CMFCorePermissions.ManagePortal, 'addScheduleElement')
    def addScheduleElement( self, method, temporal_expr, prefix='', title='', args=(), kwargs={} ):
        """
           Adds task to schedule and returns task id
        """
        if not self.getSize():
            self.idx = 0
        idx = getattr(self, 'idx', 0) + 1
        id = cookId( container=self._schedule, mask='X%s-%s' % ( prefix, '%s-%s' ), prefix='_thread_', idx=idx )

        element = ScheduleElement( id=id,
                                   title=title,
                                   method_name=method.im_func.func_name,
                                   target_object= method.im_self,
                                   temporal_expr=temporal_expr,
                                   args=args,
                                   kwargs=kwargs
                                 )

        try:
            self.getSchedule()._setObject(id, element) #, set_owner=0
            self.idx = idx
        except Exception, message:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            info = 'id: %s, type: %s, value: %s' % ( id, exc_type, exc_value )

            LOG( Config.ProductName, ERROR, 'Cannot add schedule element: %s\ntitle: %s\nmessage: %s' % ( \
                info, str(message) ) )

        #self.resetDispatcher()
        return id

    security.declareProtected(CMFCorePermissions.View, 'hasScheduleElement')
    def hasScheduleElement( self, id ):
        return self.getSchedule().has_key( id )

    security.declareProtected(CMFCorePermissions.View, 'getScheduleElement')
    def getScheduleElement( self, id ):
        return self.getSchedule()._getOb( id, None )

    security.declareProtected(CMFCorePermissions.ManagePortal, 'delScheduleElement')
    def delScheduleElement( self, ids, force=1 ):
        """
            Removes schedule elements.

            Arguments:

                'ids' -- Schedule elements ids list.

                'force' -- Whether to swallow AttributeError while trying to 
                           remove the nonexistent object.
        """
        if type(ids) not in ( ListType, TupleType, ):
            ids = [ids]

        for id in ids:
            try:
                self.getSchedule()._delObject( id )
            except ( KeyError, AttributeError ):
                if not force:
                    raise 

        #self.resetDispatcher()

    security.declareProtected(CMFCorePermissions.View, 'getSchedule')
    def getSchedule( self ):
        """
            Returns schedule instance
        """
        #self._initstate()
        return self._schedule

    security.declareProtected(CMFCorePermissions.View, 'getSchedulerName')
    def getSchedulerName( self ):
        return '/'.join( self.getPhysicalPath() )

    security.declareProtected(CMFCorePermissions.ManagePortal, 'checkDaemon')
    def checkDaemon( self ):
        """
            Returns 1 if corresponding thread has started else 0
        """
        logger.info( 'Scheduler dispatchers: %s, oid: %s' % ( _dispatchers, repr(self._p_oid) ) )
        for thread in threading.enumerate():
            logger.info("active thread name: %s" % thread.getName())
            if thread.getName() == 'PortalScheduler_%s' % self.getSchedulerName():
                return 1
        return 0

    security.declareProtected(CMFCorePermissions.ManagePortal, 'startDaemon')
    def startDaemon( self, postpone=None ):
        """
            Starts scheduler thread in case it is not running already
        """
        if Config.DisableScheduler or self.checkDaemon():
            return None

        dispatcher = EventDispatcher( self )
        dispatcher.setDaemon(1)

        _dispatchers[ self._p_oid ] = dispatcher
        if postpone is not None:
            return dispatcher

        dispatcher.start()
        time.sleep( random() )

        LOG( Config.ProductName, INFO, 'Started scheduler thread' )
        return dispatcher

    security.declareProtected(CMFCorePermissions.ManagePortal, 'stopDaemon')
    def stopDaemon( self ):
        """
            Stops scheduler thread
        """
        logger.info( 'Scheduler dispatchers: %s, oid: %s' % ( _dispatchers, repr(self._p_oid) ) )

        dispatcher = _dispatchers.get( self._p_oid )
        if dispatcher is not None:
            logger.info( 'Stop dispatcher thread for scheduler %s' % self.getSchedulerName() )
            dispatcher.terminate()
            return 1

        LOG( Config.ProductName, INFO, 'No dispatcher thread for scheduler %s' % self.getSchedulerName() )
        logger.error( 'No dispatcher thread for scheduler %s' % self.getSchedulerName() )

        return 0

    security.declareProtected(CMFCorePermissions.ManagePortal, 'resetDispatcher')
    def resetDispatcher( self, reason=None ):
        """
            Restarts scheduler thread
        """
        dispatcher = _dispatchers.get( self._p_oid )
        if dispatcher:
            dispatcher.reset( reason )

    def manage_afterAdd( self, item, container ):
        """
            Please note that this method commits a transaction in order to 
            start scheduling thread
        """
        self.register()

        if Config.AutoStartDaemonThreads:
            #transaction.commit()
            self.REQUEST._hold( DeferredStarter(self) )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'isRegistered' )
    def isRegistered( self ):
        root = self.getPhysicalRoot()
        schedulers_list = root._getOb( 'SchedulersList', None )
        if not schedulers_list:
            return None

        return schedulers_list.isRegistered( self )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'register' )
    def register( self ):
        root = self.getPhysicalRoot()
        schedulers_list = root._getOb( 'SchedulersList', None )
        if schedulers_list is None:
            root.manage_addProduct['PortalScheduler'].createSchedulersList()
            schedulers_list = root._getOb( 'SchedulersList', None )

        schedulers_list.registerScheduler( self )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'unregister' )
    def unregister( self ):
        root = self.getPhysicalRoot()
        schedulers_list = root._getOb( 'SchedulersList', None )
        if schedulers_list:
            schedulers_list.unregisterScheduler( self )

    def manage_beforeDelete( self, item, container ):
        self.stopDaemon()
        self.unregister()

    security.declareProtected( CMFCorePermissions.ManagePortal, 'manage_scheduler' )
    def manage_scheduler( self, REQUEST ):
        """
            ZMI support
        """
        r = REQUEST.has_key
        uname = _getAuthenticatedUser(self).getUserName()

        if r('start'):
            action = 'start'
            self.startDaemon()

        elif r('stop'):
            action = 'stop'
            self.stopDaemon()

        elif r('restart'):
            action = 'restart'
            self.stopDaemon()
            self.startDaemon()

        elif r('register'):
            action = 'register'
            self.register()

        elif r('unregister'):
            action = 'unregister'
            self.unregister()

        else:
            action = 'undefined'

        logger.info( 'manage scheduler: action %s, uname %s' % ( action, uname ) )
        REQUEST['RESPONSE'].redirect( self.absolute_url() + '/manageSchedulerForm' )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'manage_queue' )
    def manage_queue( self, REQUEST ):
        """
            ZMI support
        """
        queue = self.getSchedule().getEventQueue()
        r = REQUEST.has_key
        if r('refresh'):
            #queue.invalidate()
            self.resetDispatcher()

        REQUEST['RESPONSE'].redirect( self.absolute_url() + '/manageEventsQueueForm' )

    security.declareProtected( CMFCorePermissions.ManagePortal, 'manage_schedule' )
    def manage_schedule( self, REQUEST ):
        """
            ZMI support
        """
        schedule = self.getSchedule()
        action = REQUEST.get('action')
        uname = _getAuthenticatedUser(self).getUserName()

        if action == 'remove':
            self.stopDaemon()
            ids = REQUEST.get('ids') or []
            for id in ids:
                schedule._delObject( id )
            self.startDaemon()

        elif action == 'suspend':
            ids = REQUEST.get('ids') or []
            for id in ids:
                ob = schedule._getOb( id )
                ob.suspend()

        elif action == 'resume':
            ids = REQUEST.get('ids') or []
            for id in ids:
                ob = schedule._getOb( id )
                ob.resume()

        elif action == 'run':
            ids = REQUEST.get('ids') or []
            for id in ids:
                ob = schedule._getOb( id )
                ob.run()

        else:
            action = 'undefined'
            ids = None

        logger.info( 'manage schedule: action %s, uname %s, ids %s' % ( action, uname, ids ) )
        REQUEST['RESPONSE'].redirect( self.absolute_url() + '/manageScheduleForm' )


class EventDispatcher( threading.Thread ):

    running = False

    min_timestamp = DateTime(1970)
    max_timestamp = DateTime(9999)

    def __init__( self, scheduler ):
        self.scheduler_path = scheduler.getPhysicalPath()

        self.CheckEvent = threading.Event()
        self.TaskSemaphore = threading.Semaphore( Config.MaxThreadsCount )

        threading.Thread.__init__( self, name='PortalScheduler_%s' % scheduler.getSchedulerName() )

    def reset( self, reason=None ):
        if reason is not None:
            if not reason.listOccurences( self.min_timestamp, self.max_timestamp ):
                return
            
        self.CheckEvent.set()

    def run( self ):
        """
            Start as main schedule thread
        """
        try:
            self._activate()
        except: pass

    def _activate( self ):
        product_name = Config.ProductName 
        scheduler_path = self.scheduler_path
        app = Zope2.bobo_application()
        schedule = None

        try:
            scheduler = app.unrestrictedTraverse( self.scheduler_path, None )
            if scheduler is None:
                LOG( product_name, ERROR, 'Error traversing scheduler %s' % '/'.join( scheduler_path ) )
                return

            schedule = scheduler.getSchedule()
            queue = schedule.getEventQueue( reset=True )

            CheckEvent = self.CheckEvent
            self.running = True
            logger.info('run started')

            while self.running:
                try:
                    app._p_jar.sync()
                except:
                    LOG( product_name, ERROR, 'Connection Error %s: [%s]' % ( \
                         '/'.join( scheduler_path ), self.running ), \
                         error=exc_info() )
                    break

                try:
                    queue = schedule.getEventQueue( reset=1 )
                    event = schedule.getNextEvent()

                    if event is not None and event.waitTillStart( CheckEvent ):
                        self.TaskSemaphore.acquire()
                        event.setDaemon(1)
                        event.setSemaphore( self.TaskSemaphore )
                        event.start()

                        del event
                        del queue.queue[0]
                    else:
                        # No events left in the queue or CheckEvent flag was risen.
                        #if not CheckEvent.isSet():
                        # Just waiting for the queue to expire.
                        if queue.expires:
                            delay = queue.expires - now()
                            CheckEvent.wait( delay.seconds )
                        if not CheckEvent.isSet():
                            # Queue expired normally. Just update the queue, no need to 
                            queue.invalidate()

                    # Check whether it is required to update ZODB connection and
                    # invalidate events queue.
                    if CheckEvent.isSet():
                        queue.invalidate()

                    CheckEvent.clear()

                except ( ConflictError, ReadConflictError ):
                    exc_type, exc_value, exc_traceback = exc_info()
                    LOG( product_name, TRACE, 'resolving %s: [%s]' % ( exc_type, '/'.join( scheduler_path ) ) )
                    time.sleep( random() )

                except:
                    LOG( product_name, ERROR, 'EventDispatcher Error %s: [%s]' % ( \
                         '/'.join( scheduler_path ), self.running ), \
                         error=exc_info() 
                         )

            logger.info('run finished')

        finally:
            if schedule is not None:
                schedule.deleteEventQueue()

            if app is not None:
                app._p_jar.close()
                LOG( product_name, INFO,
                     'Terminating dispatcher thread for scheduler %s' % '/'.join( scheduler_path ),
                    )

    def terminate( self ):
        LOG( Config.ProductName, INFO, 'run terminate' )
        self.running = False
        self.CheckEvent.set()
        time.sleep(1)


class DeferredStarter:
    def __init__( self, scheduler ):
        self.scheduler = scheduler

    def __del__( self):
        # N.B.: if app installation failed dispatcher thread exits immediately with error.
        self.scheduler.startDaemon()
        del self.scheduler
