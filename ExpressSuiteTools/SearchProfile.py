"""
Shortcuts are references to other objects within the same CMF site.
$Id: SearchProfile.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 18/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from copy import deepcopy
from random import randrange
from types import DictType

from AccessControl import ClassSecurityInfo
from AccessControl import Permissions as ZopePermissions
from Acquisition import aq_get

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName

import Features
from SimpleAppItem import SimpleAppItem
from Utils import InitializeClass, joinpath, GetSessionValue

from logging import getLogger
logger = getLogger( 'SearchProfile' )


factory_type_information = ( { 'id'             : 'Search Profile'
                             , 'meta_type'      : 'Search Profile'
                             , 'title'          : 'Search Profile'
                             , 'description'    : """ Stored search profile """
                             , 'icon'           : 'view.gif'
                             , 'product'        : 'ExpressSuiteTools'
                             , 'factory'        : 'addSearchProfile'
                             , 'permissions'    : ( ZopePermissions.search_zcatalog, )
                             , 'disallow_manual': 0
                             , 'actions'        :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'Execute'
                                  , 'action'        : 'execute'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'metadata'
                                  , 'name'          : 'Metadata'
                                  , 'action'        : 'search_profile_metadata'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  }
                                )
                             }
                           ,
                           )

def addSearchProfile( self, id, query_id=None, title='', description='', REQUEST=None, query=None ):
    """
        Add a Search Profile
    """
    if query is None:
        request = REQUEST or aq_get( self, 'REQUEST' )
        query = query_id and GetSessionValue( self, 'search_%s' % query_id, None, request ) or None

    self._setObject( id, SearchProfile( id, title, description, query ) )

    if REQUEST is not None:
        return self.redirect( message="Search profile added.", REQUEST=REQUEST )


class isSearchProfile( Features.Feature ): pass
Features.isSearchProfile = isSearchProfile


class SearchProfile( SimpleAppItem ):
    """
        A persistent Search Profile
    """
    _class_version = 1.0

    meta_type = 'Search Profile'
    portal_type = 'Search Profile'

    __implements__ = Features.isSearchProfile, \
                     SimpleAppItem.__implements__

    __unimplements__ = ( Features.isCategorial, )

    security = ClassSecurityInfo()
    #security.declareProtected( CMFCorePermissions.View, 'query' )

    def __init__( self, id, title='', description='', query=None ):
        """
        """
        SimpleAppItem.__init__( self, id )

        self.setTitle( title )
        self.setDescription( description )
        self.setQuery( query )

    security.declareProtected( CMFCorePermissions.View, 'getQuery' )
    def getQuery( self ):
        """
            Returns query object
        """
        #logger.info('getQuery %s' % self.query )
        return self.query

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setQuery' )
    def setQuery( self, query ):
        """
            Sets new query object
        """
        if query is None:
            self.query = SearchQuery()
        elif type(query) is DictType:
            self.query = SearchQuery( params=query )
        else:
            self.query = query.clone()
        self.query.id = None
        #logger.info('setQuery %s' % self.query )

    security.declareProtected( CMFCorePermissions.View, 'execute' )
    def execute( self, REQUEST=None ):
        """
            Redirects to the search results page
        """
        REQUEST = REQUEST or aq_get( self, 'REQUEST' )
        if REQUEST is None:
            return ''

        params = {}
        params['profile_id'] = self.getUid()
        params['batch_length'] = 5
        #if REQUEST.has_key('sorting'):
        #    params['sorting'] = 'custom'
        #    params['sort_on'] = REQUEST.get('sort_on', None)
        #    params['sort_order'] = REQUEST.get('sort_order', None)
        #logger.info('execute %s' % params['profile_id'] )

        return self.redirect( action='search_results', params=params, REQUEST=REQUEST )

InitializeClass( SearchProfile )


class SearchQuery:

    security = ClassSecurityInfo()
    security.setDefaultAccess(1)

    text = ''
    oid = ''
    title = ''
    description = ''
    creation = ('','')
    owners = ()
    objects = ['bodies']
    types = ()
    fields = ()
    scope = 'global'
    sorting = 'relevance'
    location = None
    filters = ()
    transitivity = None
    category = None
    state = None
    registry_id = ''
    message = None
    derivatives = None # if 1 - mean hasBase(category)

    def __init__( self, id=None, params=None ):
        if params:
            self.__dict__ = deepcopy( params )
        self.id = id

    def __guarded_setattr__( self, name, value ):
        setattr( self, name, value )

    def getId( self ):
        if self.id is None:
            self.id = str( randrange(1000000000) )
        return self.id

    def copy( self ):
        return self.__class__(None, self.__dict__)

    clone = copy

    def filter( self, results, parent ):
        for id in self.filters:
            if _registered_filters.has_key( id ):
                results = _registered_filters[ id ]( results, query=self, parent=parent )
        return results

InitializeClass( SearchQuery )


_registered_filters = {}

def registerFilter( id, filter ):
    _registered_filters[ id ] = filter
