"""
Portal Scheduler. Schedule class

*** Checked 06/03/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import Zope2
import transaction

#import ThreadLock

import sys
from bisect import insort
from types import StringType

from threading import Thread, Event as ThreadingEvent
from time import time

from mx.DateTime import RelativeDateTime, now

from AccessControl import ClassSecurityInfo, SecurityManagement, User
from AccessControl.Permissions import access_contents_information, view_management_screens
from Acquisition import Implicit, aq_parent

from Globals import InitializeClass, DTMLFile, Persistent

from ZODB.POSException import ConflictError, ReadConflictError
from OFS.Folder import Folder

from Products.CMFCore import permissions as CMFCorePermissions

import Config
from Config import States
from Utils import ResolveConflict

from zLOG import INFO, ERROR
from Logger import LOG


class EventQueue:

    __allow_access_to_unprotected_subobjects__ = 1

    def __init__( self, schedule, expires=None ):
        self.queue = []
        self.schedule = schedule
        self.expires = expires

    def isExpired( self ):
        return not self.expires or self.expires < now()

    def invalidate( self ):
        self.expires = None

    def refresh( self ):
        self.queue = []
        created = now()
        expires = created + self.getExpirationInterval()
        delay = float( 3 ) / 86400
        removed = 0
        errors = 0

        try:
            scheduler_name = self.schedule.getSchedulerName()
        except AttributeError:
            scheduler_name = None

        for id, element in self.schedule.objectItems():
            state = element.getState()
            effective_date = None
            if state == States.Zombie:
                # BUG (check real effective date with delay in the running threads before the item removal)
                try:
                    effective_date = element.getTemporalExpression().getRealDate()
                except:
                    pass
                if effective_date is None:
                    LOG( scheduler_name, INFO, 'Bad real date, id: %s' % id )
                elif element.isAutoRemovable() and created > effective_date + delay:
                    try:
                        self.schedule._delObject( id )
                        removed += 1
                    except:
                        method = getattr( element, 'method_name', None )
                        LOG(scheduler_name, ERROR, 'cannot remove: id %s, method %s' % ( id, method ))
                        errors += 1
                continue
            elif state == States.Suspended: 
                continue

            occurences = element.listOccurences( created, expires ) or []
            for datetime in occurences:
                insort( self.queue, (datetime, id) )

        self.expires = expires

        transaction.get().commit()

        if not ( removed or errors ):
            return

        LOG( scheduler_name, INFO, 'Queue refresh (%s events, %s removed, %s errors)' % ( \
             len(self.queue), removed, errors ) \
            )
    """
    def refresh( self ):
        self.queue = []
        created = now()

        start_from = created
        if self.expires is not None and self.expires < created:
            start_from = self.expires

        expires = created + self.getExpirationInterval()

        should_be_commit = False
        removed = 0
        for id, element in list(self.schedule.objectItems()):
            state = element.getState()
            if state == States.Zombie:
                if element.isAutoRemovable():
                    self.schedule._delObject( id )
                    should_be_commit = True
                    removed += 1
                continue
            elif state == States.Suspended:
                continue

            occurences = element.listOccurences( start_from, expires ) or []
            for datetime in occurences:
                insort( self.queue, (datetime, id) )

        self.created = created
        self.expires = expires

        if should_be_commit:
            transaction.commit()

        try:
            scheduler_name = self.schedule.getSchedulerName()
        except AttributeError:
            scheduler_name = None

        LOG( scheduler_name, INFO, 'Queue refresh (%s events, %s removed, should_be_commit: %s)' % ( \
             len(self.queue), removed, should_be_commit ) \
            )
    """
    def getExpirationInterval( self ):
        return Config.QueueExpirationIterval

    def __len__( self ):
        return len( self.queue )

_event_queues = {}
_marker = []


class ScheduleEvent( Thread ):

    #lock = ThreadLock.allocate_lock()

    def __init__( self, start_date, element, scheduler_path, semaphore=None ):
        if type( element ) is not StringType:
            element = element.getId()

        Thread.__init__( self, name=element )
        self.id = time()
        self.element_id = element
        self.start_date = start_date
        self.scheduler_path = scheduler_path
        self.semaphore = semaphore
        self.error = None

    def run( self ):
        """
            Starts event action.
            This method is executed within the separate ZODB connection.
        """
        self._app = Zope2.bobo_application()
        conflict_timeout = float( Config.ConflictTimeout )

        res = None

        #self.lock.acquire()

        try:
            try:
                LOG( self.scheduler_path, INFO, 'running action for: %s [%s]' % ( self.element_id, self.id ) )
                element = self.getScheduleElement()

                if element is not None:
                    system = User.UnrestrictedUser( 'System Processes','',('manage', 'Member','Manager',), [] )
                    SecurityManagement.newSecurityManager( None, system )

                    res = element.doAction()

                    #if type(res) == type({}) and res.get('auto_remove'):
                    #    element.setTemporalExpression( None )
                    #    element.auto_remove = True

                    SecurityManagement.noSecurityManager()

                transaction.get().commit()

            except ( ConflictError, ReadConflictError ):
                LOG( self.scheduler_path, ERROR, 'Conflict error while executing action for: %s [%s]' % ( \
                     self.element_id, self.id ) )

                ThreadingEvent.wait( conflict_timeout )
                self.error = 1

            except:
                info = 'id: %s, scheduler: %s' % ( self.element_id, self.id )
                LOG( self.scheduler_path, ERROR, 'error while executing action for %s' % ( \
                     info ), error=sys.exc_info() )

                transaction.get().abort()

            else:
                LOG( self.scheduler_path, INFO, 'exiting action for: %s [%s], result: %s' % ( \
                     self.element_id, self.id, res ) )

        finally:
            self._app._p_jar.close()
            del self._app

            semaphore = self.getSemaphore()
            if semaphore:
                semaphore.release()

            #self.lock.release()

    def wasAborted( self ):
        error = getattr(self, 'error', None)
        return error and 1 or 0

    def waitTillStart( self, threading_event=None ):
        if threading_event is None:
            threading_event = ThreadingEvent()

        seconds = self.getRemainingTime().seconds
        if seconds > 0:
            threading_event.wait( seconds )
        if threading_event.isSet():
            return None

        return 1

    def getRemainingTime( self ):
        return self.start_date - now()

    def getScheduleElement( self ):
        ob = None
        scheduler = self._getScheduler()
        if scheduler is not None:
            schedule = scheduler.getSchedule()
            ob = schedule._getOb( self.element_id, None )
            if ob is None:
                LOG( self.scheduler_path, INFO, 'element not found: [%s], %s' % ( \
                    self.element_id, self.scheduler_path ) )
        else:
            LOG( self.scheduler_path, INFO, 'scheduler not found: [%s], %s' % ( \
                self.element_id, self.scheduler_path ) )
        return ob

    def setSemaphore( self, semaphore ):
        self.semaphore = semaphore

    def getSemaphore( self ):
        return self.semaphore

    def _getScheduler( self ):
        return self._app.unrestrictedTraverse( self.scheduler_path, None )

InitializeClass( ScheduleEvent )


class Schedule( Persistent, Folder, Implicit ):

    security = ClassSecurityInfo()
    security.setDefaultAccess( 1 )

    manage_options=(
        ({'label':'Contents', 'action':'manage_main',},
         ) + Folder.manage_options[1:]
        )

    security.declareProtected(view_management_screens, 'manage_main')
    manage_main = DTMLFile('contents', globals())

    def __init__( self, id=None ):
        if id is not None:
            self.id = id
        self._tree = {}
        self._count = 0

    def _p_resolveConflict( self, oldState, savedState, newState ):
        """
            Try to resolve conflict between container's objects
        """
        oldState = ResolveConflict('Schedule', oldState, savedState, newState, '_tree', \
                                    mode=2 \
                                    )
        oldState['_count'] = len(oldState['_tree'].keys())
        return oldState

    security.declareProtected( CMFCorePermissions.View, 'getNextEventInfo' )
    def getNextEventInfo( self ):
        queue = self.getEventQueue()
        # XXX: Should be len( queue )
        if len( queue.queue ):
            return queue.queue[0]
        return None

    security.declareProtected( CMFCorePermissions.View, 'getNextEvent' )
    def getNextEvent( self ):
        event_info = self.getNextEventInfo()
        if event_info:
            start_date, element_id = event_info
            scheduler_path = '/'.join( self.getPhysicalPath() )
            return ScheduleEvent( start_date, element_id, scheduler_path )
        return None

    security.declareProtected( CMFCorePermissions.ManagePortal, 'getEventQueue' )
    def getEventQueue( self, reset=None ):
        if reset:
            self.deleteEventQueue()
        try:
            queue = _event_queues[ self._p_oid ]
        except KeyError:
            queue = _event_queues[ self._p_oid ] = EventQueue( self )
        if queue.isExpired():
            queue.refresh()
        return queue

    security.declarePrivate( 'deleteEventQueue' )
    def deleteEventQueue( self ):
        try:
            del _event_queues[ self._p_oid ]
        except: #KeyError
            pass

    def change_state( self, tree, count=None ):
        self._tree = tree
        if count is not None:
            self._count += count
        self._p_changed = 1

    def getSchedulerName( self ):
        pass

    def objectCount( self ):
        """Returns the number of items in the folder."""
        return self._count or 0

    def has_key(self, id):
        """Indicates whether the folder has an item by ID."""
        return self._tree.has_key(id)

    def objectIds( self, spec=None ):
        """Returns a list of subobject ids of the current object."""
        return self._tree.keys()

    def objectItems( self ):
        """Returns a list of (id, subobject) tuples of the current object."""
        return self._tree.items()

    def getSortedObjectItems( self ):
        """Returns sorted events list."""
        tree = self.objectItems()
        tree.sort( lambda x, y: cmp(x[1].getNextOccurenceDate(), y[1].getNextOccurenceDate()) )
        return tree

    def objectValues( self ):
        """Returns a list of actual subobjects of the current object."""
        return self._tree.values()

    def _setObject( self, id, object ):
        self._setOb( id, object )

    def _delObject( self, id ):
        self._delOb( id )

    def _getOb( self, id, default=_marker ):
        """Return the named object from the folder."""
        tree = self._tree
        if default is _marker:
            ob = tree[id]
            return ob.__of__(self)
        ob = tree.get(id, _marker)
        if ob is _marker:
            return default
        return ob.__of__(self)

    def _setOb( self, id, object ):
        """Store the named object in the folder."""
        if not id: return
        tree = self._tree
        tree[id] = object
        self.change_state( tree, 1 )

    def _delOb( self, id ):
        """Remove the named object from the folder."""
        tree = self._tree
        if not tree.has_key(id): return
        del tree[id]
        self.change_state( tree, -1 )

    # Aliases for mapping-like access.
    __len__ = objectCount
    keys = objectIds
    values = objectValues
    items = objectItems

    # backward compatibility
    hasObject = has_key

    security.declareProtected(access_contents_information, 'get')
    def get( self, name, default=None ):
        return self._getOb( name, default )

InitializeClass( Schedule )
