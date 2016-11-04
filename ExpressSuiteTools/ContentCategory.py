"""
ContentCategory class (SQL adapted)
$Id: ContentCategory.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 07/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys, re
from types import StringType, ListType, TupleType
from Acquisition import aq_base, aq_inner, aq_chain
from AccessControl import ClassSecurityInfo
from DateTime import DateTime
from ExtensionClass import Base

from ZODB.POSException import ConflictError

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName, _checkPermission

import Features
from Utils import InitializeClass, getObjectByUid

from logging import getLogger
logger = getLogger( 'ContentCategory' )


class ContentCategory( Base ):
    """
        Content category type
    """
    _class_version = 1.0

    __implements__ = ( Features.isCategorial, )

    security = ClassSecurityInfo()

    # default attribute values
    category = None

    security.declareProtected( CMFCorePermissions.View, 'isInCategory' )
    def isInCategory( self, category, strict=1 ):
        """
            Checks whether the document belongs to a given category.

            Arguments:

                'category' -- Either category definition object or category
                              identifier to check against.  Alternatively,
                              a list of definition objects or identifiers
                              may be given.

                'strict' -- Boolean flag, true by default. If false,
                            the category inheritance hierarchy is checked
                            additionally.

            Result:

                Boolean.
        """
        if type(category) in ( TupleType, ListType ):
            categories = category
        else:
            categories = [category]

        mine = self.getCategory()

        for category in categories:
            if mine == category:
                return 1
            if not strict and category in mine.listBases( recursive=1 ):
                return 1

        return 0

    def setCategory( self, category ):
        """
            Associates the document with a given category.

            Arguments:

                'category' -- Either a category definition object or a category
                              id string.
        """
        if type(category) is StringType:
            metadata = getToolByName(self, 'portal_metadata', None)
            x = metadata is not None and metadata.getCategoryById(category)
        else:
            x = category

        self.category = x.getId()

        for attr in x.listAttributeDefinitions():
           id = attr.getId()
           if self.getCategoryAttribute(id, None) is None:
                value = ''
                if attr.Type() == 'date':
                    value = DateTime()
                # self.setCategoryAttribute(id, value)
                self.setCategoryAttribute(id, value, reindex=0)

        if hasattr(aq_base(self), 'reindexObject'):
            self.reindexObject( idxs=['category','hasBase','CategoryAttributes'] )

    def Category( self ):
        """
            Returns the document's category id.

            Note:

                This method is obsolete, getCategory should be used instead.
        """
        category = self.category
        if not category:
            category = self._getDefaultCategory()
            return category and category.getId()

        return category

    def getCategory( self ):
        """
            Returns the document's category.

            Result:

                Category definition object.
        """
        category = self.category
        if type(category) is StringType:
            metadata = getToolByName(self, 'portal_metadata', None)
            category = metadata is not None and metadata.getCategoryById(category)

        if not category:
            try: category = self._getDefaultCategory()
            except: category = None

        return category

    def _getDefaultCategory( self ):
        """
            Returns the object's default category
        """
        metadata = getToolByName(self, 'portal_metadata', None)
        categories = metadata is not None and metadata.listCategories(self)
        if categories:
            return categories[0]
        return None

    def SearchableProperty( self ):
        res = ''
        for attr, value in self.listCategoryAttributes():
            res += "[" + attr.getId() + "]:'" + str(value) + "' "
        return res

    def setCategoryAttribute( self, attr, value=MissingValue, reindex=1 ):
        """
            Sets the value of the document category attribute.

            Arguments:

                'attr' -- Either a CategoryAttribute class instance or an
                          attribute id string.

                'value' -- Attribute value. If no value given, attribute's
                           default value will be used.

            Result:

                Boolean. Result value is True in case the attribute were
                successfully added to the object or False otherwise.
        """
        category = self.getCategory()

        if category is None:
            return None

        a = attr
        v = value

        if type(a) is StringType:
            a = category.getAttributeDefinition( a )
        if v and type(v) == type(''):
            # Remove SQL-command delimeter
            v = re.sub(r'\|', r'-', v)

        if a is None:
            raise KeyError, 'Invalid category attribute specified'

        if not ( self.checkAttributePermission(a.getId(), CMFCorePermissions.ModifyPortalContent) or \
            _checkPermission('Manage properties', self) ):
            return 0

        if v is MissingValue:
            v = a.getDefaultValue()

        attr_type = a.Type()
        if attr_type == 'userlist' and type(v) not in ( TupleType, ListType ):
            v = [ v ]

        name = a.getId()
        sheet = self._getCategorySheet()
        attr_value = sheet.getProperty( name, None )

        if attr_type == 'date':
            if type(v) is StringType and v[0:2] == '__':
                if sheet.hasProperty( name ):
                    sheet.manage_delProperties( [name] )
                attr_type = 'string'
            else:
                a = self.getCategoryAttribute( name )
                if a and type(a) is StringType:
                    sheet.manage_delProperties( [name] )

        elif attr_type == 'table':
            if v and not v.has_key('values'):
                v['values'] = sheet.getProperty( name, {} ).get('values') or []

        if v is None:
            if not sheet.hasProperty( name ):
                return 0
            sheet.manage_delProperties( [name] )
        elif sheet.hasProperty( name ):
            sheet.manage_changeProperties( { name: v } )
        else:
            if attr_type == 'lines' or attr_type == 'int' or attr_type == 'float':
                attr_type = 'string'
            sheet.manage_addProperty( name, v, attr_type )

        if attr_type == 'link' and not a.getComputedDefault():
            # Copy/Clear attributes from the source document
            attr_value = v or attr_value
            if not attr_value:
                return None

            source = getObjectByUid( self, attr_value, 'isCategorial' )
            if source is None:
                return None
            source_category = source.getCategory()
            if source_category is None:
                return None

            RN = source_category.getRN()
            RD = source_category.getRD()
            if not RN and not RD:
                return None

            msg = getToolByName( self, 'msg' )

            for adef in category.listAttributeDefinitions():
                adef_id = adef.getId()
                if not adef_id.startswith( name + '_' ):
                    continue
                x = adef_id[len(name)+1:]
                if RN and x == 'RN':
                    adef_value = v and source.getCategoryAttribute( RN, None ) or msg('NO/RN')
                elif RD and x == 'RD':
                    adef_value = v and source.getCategoryAttribute( RD, None ) or None
                else:
                    continue
                if adef_value is not None:
                    self.setCategoryAttribute( adef, adef_value, reindex=reindex )
                elif sheet.hasProperty( adef_id ):
                    sheet.manage_delProperties( [adef_id] )

        if reindex and hasattr( aq_base(self), 'reindexObject' ):
            self.reindexObject( idxs=['CategoryAttributes'] )

        return 1

    def listCategoryAttributes( self ):
        """
            Lists the document category attributes.

            Result:

                List of the attribute definition, attribute value pairs.
        """
        category = self.getCategory()

        if category is not None:
            return [ ( attr, self.getCategoryAttribute(attr) ) for attr in category.listAttributeDefinitionsBySortkey() \
                if attr.getId() not in ['IN_Rep'] ]

        return []

    def CategoryAttributes( self ):
        """
            Indexing routine. Returns the document category attributes list.

            Result:

                Dictionary (attribute id -> attribute value).
        """
        r = {}

        category = self.getCategory()
        if category is None: # or not self.implements('isDocument'):
            return r

        for attr in category.listAttributeDefinitions():
            typ = attr.Type()
            # XXX definitely should have attr.isIndexable
            if typ in ['link', 'table']:
                continue
            value = self.getCategoryAttribute( attr, None )
            # XXX should fix attributes index instead
            if typ in ['lines','userlist'] and value is None:
                value = []
            r[ attr.getId() ] = value

        return r

    def checkAttributePermission( self, attr, perm ):
        """
            Checks whether the user has given permission given on category
            attribute in current object state.

            Arguments:

                'attr' -- Either a CategoryAttribute class instance or an
                          attribute id string.

                'perm' -- Permission to test. Only two permissions have sense
                          here - 'View' and 'Modify portal content'

            Note: This is not the 'real' Zope security check. There is no
                'acquired' roles for permissions while check.

            Result:

                Boolean. Result value is True in case the user has given
                permission on given category attribute or False otherwise.
        """
        #It should work as follows (numbers denotes the order of roles search):
        #
        #for each attribute in each state may be set:
        #   list of roles who can view attr and
        #   list of roles who can change attr in current state
        #1. If roles are set (changed) for attribute in the state:
        #   all users having one of listed roles can access to the attribute value.
        #
        #2. If roles are not yet set (changed) for attribute, try to acquire roles from state:
        #   for viewing - permission 'View',
        #   for editing - permission 'Modify portal content'
        #
        #3. If there is category inheritance and in the parent category there is
        #   same state and same attribute, try to do as 1,2 but in parent category
        #
        #4. And so forth.

        category = self.getCategory()

        if not category:
            return None

        if type(attr) is StringType:
            attr = category.getAttributeDefinition(attr)

        if attr is None:
            return None

        attribute_id = attr.getId()

        membership = getToolByName(self, 'portal_membership', None)
        workflow = getToolByName( self, 'portal_workflow', None )
        if None in ( membership, workflow ):
            return 0

        user = membership.getAuthenticatedMember()
        user_roles = user.getRolesInContext(self)

        state = workflow.getStateFor( self )
        if state is None:
            #Most likely - no default states in category settings.
            return 0

        bases = [ category ]
        bases.extend( category.listBases(expand=1) )

        for category in bases:
            wf = category.__of__(self).getWorkflow()
            result = wf.getAttributePermissionInfo( state, attribute_id, perm )

            if result['acquired']: # and not result['roles']:
                #use parent's props
                sd = getattr( wf.states, state, None )
                if sd is None:
                    continue

                if wf.states.isPrivateItem( sd ):
                    #simply check permission
                    #...hm, is it correct?
                    return _checkPermission( perm, self )
            else:
                for u_role in user_roles:
                    if u_role in result['roles']:
                        return 1
                return 0
        return 0

    security.declareProtected( CMFCorePermissions.View, 'getCategoryAttribute' )
    def getCategoryAttribute( self, attr, default=None ):
        """
            Returns the value of the document category attribute.

            Arguments:

                'attr' -- Either a CategoryAttribute class instance or an
                          attribute id string.

                'default' -- Default attribute value to be used in case it was
                             not found in the document.

            Result:

                Attribute value.
        """
        if type(attr) is StringType:
            category = self.getCategory()
            attr = category.getAttributeDefinition( attr )

        if attr is not None and self.checkAttributePermission( attr.getId(), 'View' ):
            sheet = self._getCategorySheet()
            return sheet.getProperty( attr.getId(), default )
        else:
            return None

    def deleteCategoryAttributes( self, attrs ):
        """
            Deletes the specified attributes from the document.

            Arguments:

                'attrs' -- List of either a CategoryAttribute class instance or
                           an attribute id strings.

            Result:

                Boolean. Result value is True in case all attributes were
                successfully removed from the object or False otherwise.
        """
        sheet = self._getCategorySheet()
        names = [ type(x) is StringType and x or x.getId() for x in attrs ]
        try:
            sheet.manage_delProperties(names)
            return 1
        except ConflictError:
            logger.error('deleteCategoryAttributes ConflictError', exc_info=True)
            raise
        except:
            return None

    def hasBase( self, base=None ):
        """
            Checks whether the document's category inherits or equal to the given category.

            Result:

                Boolean value if base is not None, otherwise returns the list of
                base categories ids including the current document's category.
        """
        category = self.getCategory()

        if category is None:
            return 0 #None

        bases = category.listBases(expand=1)

        if base:
            if type(base) is StringType:
                metadata = getToolByName(self, 'portal_metadata', None)
                base = metadata is not None and metadata.getCategoryById(base)
                if not base:
                    return 0 #None

            base = aq_inner(base)
            if base == category or base in bases:
                return 1

            return 0 #None

        # Catalog indexing support
        results = [ category ]
        results.extend(bases)

        return [ x.getId() for x in results ]

    def _getCategorySheet( self ):
        """
            Returns category propertysheet
            Adds new one if no sheet found
        """
        category_id = self.Category()
        sheet_id = 'category_metadata_%s' % category_id
        sheet = self.propertysheets.get( sheet_id )
        if sheet is None:
            self.propertysheets.manage_addPropertySheet( sheet_id, sheet_id )
            sheet = self.propertysheets.get( sheet_id )
        return sheet

    def _remote_transfer( self, context=None, container=None, server=None, path=None, id=None, parents=None, recursive=None ):
        """
        """
        pass

    def _remote_delete( self, context=None, container=None, server=None, path=None, id=None ):
        """
        """
        pass

    def AuthenticatedUser( self ):
        """
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return None
        user_id = membership.getAuthenticatedMember().getUserName()
        return user_id

InitializeClass( ContentCategory )
