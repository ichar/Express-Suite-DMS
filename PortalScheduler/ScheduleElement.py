"""
Portal Scheduler. Schedule Element class

*** Checked 06/03/2009 ***

"""
from sys import exc_info
from thread import get_ident

from Acquisition import aq_parent
from OFS.SimpleItem import SimpleItem
from ZPublisher import Publish
from ZPublisher.BaseRequest import BaseRequest

from Products.Localizer.AcceptLanguage import AcceptLanguage
from Products.CMFCore.utils import getToolByName

from Config import States

from zLOG import INFO, ERROR
from Logger import LOG


class ScheduleElement( SimpleItem ):
    """
        Recurrent event definition
    """
    meta_type = 'Schedule Element'

    __resource_type__ = 'schedule'

    def __init__( self, id, title, method_name, target_object, temporal_expr, auto_remove=1,
                  args=(), kwargs={} ):
        """
            Initialize attributes
        """
        self.id = id
        self.title = title
        self.method_name = method_name
        self.target_path = target_object.getPhysicalPath()
        self.temporal_expr = temporal_expr
        self.auto_remove = auto_remove
        self.method_args = args
        self.method_kwargs = kwargs
        self.state = States.Runnable

        try:
            self.target_uid = target_object.getUid()
        except:
            self.target_uid = None

    def isAutoRemovable( self ):
        return getattr( self, 'auto_remove', None )

    def getNextOccurenceDate( self ):
        """
            Returns next scheduled event for given object
        """
        te = self.getTemporalExpression()
        return te is not None and te.nextOccurence()

    def listOccurences( self, min_date_range, max_date_range, limit=None ):
        te = self.getTemporalExpression()
        if te is not None:
            return te.listOccurences( min_date_range, max_date_range )
        return None
        
    def setTemporalExpression( self, temporal_expr ):
        """
            Sets up the task recurrence settings.

            Recurrent events are described with a temporal expression object
            assigned to the schedule element.

            Arguments:

               'te' -- TemporalExpression class instance.
        """
        #if not isinstance( temporal_expr, TemporalExpression ):
        #    raise TypeError, 'Temporal expression object expected'

        self.temporal_expr = temporal_expr

    def getTemporalExpression( self ):
        """
            Returns the task recurrence settings.

            Result:

                TemporalExpression class instance.
        """
        return getattr( self, 'temporal_expr', None )

    def setAction( self, method_name, physical_path, *args, **kwargs ):
        """
            Assigns the action to be executed when event starts.

            Action is determined by the target object referenced by it's
            physical path and method name to be called on the selected
            object. Additional arguments can be also passed to the method.

            Arguments:

              'method_name' -- string containing the callable method name.

              'physical_path' -- target object physical path.

              '*args', '**kwargs' -- additional arguments that would be passed
                                     to the method being executed.
        """
        self.method_name = method_name
        self.target_path = physical_path
        self.method_args = args
        self.method_kwargs = kwargs
        
    def getAction( self ):
        """
            Returns the action settings for the schedule element.

            Result:

                Dictionary containing the following keys: 'method_name',
                'physical_path', 'args', 'kwargs'.
        """
        return { 'method_name': self.method_name, 
                 'physical_path': self.target_path,
                 'args': self.method_args, 
                 'kwargs': self.method_kwargs
               } 

    def doAction( self ):
        """
            It runs given action
        """
        thread_id = get_ident()
        action = '%s ScheduleElement.doAction, method: [%s]' % ( thread_id, self.method_name )

        try:
            return self._activate( thread_id, action )
        except:
            LOG(action, ERROR, 'unexpected error', error=exc_info())

    def _before_activate( self, action ):
        LOG(action, INFO, 'before_activate')

        before_publish_hook = getattr(Publish, 'before_publish_hook', None)
        if callable(before_publish_hook):
            ob = self.aq_parent
            apply(before_publish_hook, ( None, ob ) )

    def _after_activate( self, action ):
        after_publish_hook = getattr(Publish, 'after_publish_hook', None)
        if callable(after_publish_hook):
            apply(after_publish_hook)

        LOG(action, INFO, 'after_activate')

    def _activate( self, thread_id, action ):
        method = None
        IsError = 0
        res = None

        self._before_activate( action )

        if hasattr(Publish, '_requests'):
            # Provide Localizer.get_request method with fake request object.
            request = BaseRequest()
            request.other['USER_PREF_LANGUAGES'] = AcceptLanguage('')
            Publish._requests[thread_id] = request

        ob = self.getTargetObject()

        if ob is None:
            LOG(action, ERROR, 'target object not found: %s' % self.id)
            IsError = 1
        else:
            method = getattr(ob, self.method_name, None)
            if method is None or not callable(method):
                LOG(action, ERROR, 'object %s has no given method' % repr(ob))
                IsError = 1

        if not IsError:
            try:
                res = apply( method, self.method_args, self.method_kwargs )
            finally:
                if hasattr(Publish, '_requests') and Publish._requests.has_key(thread_id):
                    Publish._requests[thread_id].close()
                    del Publish._requests[thread_id]

                self._after_activate( action )
        else:
            self._after_activate( action )

        return res

    def getTargetObject( self ):
        """
            Returns target object by traverse or self uid
        """
        ob = None
        # try to get traverse
        try:
            if self.target_path:
                ob = self.unrestrictedTraverse( self.target_path, None )
        except:
            pass
        # if OK return object
        if ob is not None:
            return ob
        # otherwise check the given uid via portal catalog
        # BE CAREFULLY! new connection will be open(!)
        try:
            catalog = getToolByName( self, 'portal_catalog', None )
            return catalog.unrestrictedGetObjectByUid( self.target_uid, implements=() )
        except:
            pass

        return None

    def getState( self ):
        """
         Returns the current state of the schedule element.

         Task can be either in a 'running', 'idle' or 'disabled' state:

            'running' -- task is being executed right now.

            'idle' -- task is enabled and waiting for it's time to start.

            'disabled' -- task was disabled and will never start.

         Result:

            string
        """
        if not self.getNextOccurenceDate():
            return States.Zombie

        return self.state

    def resume( self ):
        """
            Enables the task
        """
        self.state = States.Runnable
        scheduler = aq_parent(self)
        scheduler.resetDispatcher()

    def suspend( self ):
        """
            Disables the task
        """
        self.state = States.Suspended
        scheduler = aq_parent(self)
        scheduler.resetDispatcher()

    def run( self ):
        """
            Runs the task
        """
        self.doAction()


class ScheduleResource:

    def identify( portal, object ):
        return { 'uid' : object.getId() }

    def lookup( portal, uid=None, **kwargs ):
        scheduler = getToolByName( portal, 'portal_scheduler', None )
        if scheduler is None:
            return None

        object = scheduler.getScheduleElement( str(uid) )
        if object is None:
            raise Exceptions.LocatorError( 'schedule', uid )

        return object


def initialize( context ):
    # module initialization callback
    pass
