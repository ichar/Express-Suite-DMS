"""
DepartmentDictionary class
$Id: DepartmentDictionary.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 06/05/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import DictType, ListType, TupleType, StringType

from Products.CMFCore.utils import getToolByName
from Utils import isInstance

from CustomDefinitions import _companies, _departments, DefaultSegment, CustomPredefinedFolder

COMPANIES = 0
DEPARTMENTS = 1

COMPANY_NAME = 0
COMPANY_POSTFIX = 1
COMPANY_TITLES = 2

COMPANY = 0
DEPARTMENT_POSTFIX = 1
DEPARTMENT_TITLES = 2


class DepartmentDictionary:

    __allow_access_to_unprotected_subobjects__ = 1

    def __init__( self ):
        """
            Prepared the company/department data specification. A list:

                [ companies, departments ],

            where:

                companies -- company dictionaty { company : ( name, titles ) }

                departments -- departments dictionary { department : ( company, titles ) }

                titles -- titles list.
        """
        self._data = [{}, {}]
        self._default_department = ( None, None, [None] )

        lines = _companies.split('\n')
        for line in lines:
            line = line.strip()
            if line.find(':') == -1:
                continue
            try:
                id, name, postfix, title = line.split(':')
                titles = title.split(';')
            except:
                raise ValueError, 'Line %s is invalid in %s.' % ( line, 'companies' )
            company_id = id.strip()
            company_postfix = postfix.strip()
            name = name.strip()
            company_titles = [ x.strip() for x in titles ]
            self._data[ COMPANIES ][ company_id ] = ( name, company_postfix, company_titles )

        lines = _departments.split('\n')
        for line in lines:
            line = line.strip()
            if line.find(':') == -1:
                continue
            try:
                id, company, postfix, title = line.split(':')
                titles = title.split(';')
            except:
                raise ValueError, 'Line %s is invalid in %s.' % ( line, 'departments' )
            company_id = company.strip()
            if not self._data[ COMPANIES ].has_key(company_id):
                continue
            department_id = id.strip()
            department_postfix = postfix.strip()
            department_titles = [ x.strip() for x in titles ]
            self._data[ DEPARTMENTS ][ department_id ] = ( company_id, department_postfix, department_titles )

    def _getDepartments( self, company=None ):
        """
            Returns departments by given company.

            Arguments:

                'company' -- company id (String).

            Results:

                List of tuples.
        """
        if company is None:
            return self.enumerateDepartments()
        departments = []
        for id, value in self.enumerateDepartments():
            if value[ COMPANY ] == company:
                departments.append( ( id, value ) )
        return departments

    def getIdByTitle( self, title, company=None ):
        """
            Returns id of department by gived title and given company
        """
        if type(title) is ( ListType, TupleType ):
            return title[0]
        title = title.strip()
        for id, value in self._getDepartments( company ):
            if title in value[ DEPARTMENT_TITLES ]:
                return id
        return None

    def getTitleById( self, id ):
        """
            Returns title of department by gived id
        """
        return self._data[ DEPARTMENTS ].get(id, self._default_department)[ DEPARTMENT_TITLES ][0]

    def IsDepartmentFolder( self, context, url, check_postfix=None ):
        """
            Checks if the object with given id is a department folder
        """
        if not url: return None

        x = url.rfind('/') + 1
        id = x > -1 and url[ x: ] or None
        is_department_folder = id and id in self.listDepartmentIds() and 1 or 0

        if check_postfix and is_department_folder and context is None:
            folder = context.unrestrictedTraverse( url )
            is_department_folder = folder is not None and folder.getPostfix() and 1 or 0

        return is_department_folder

    def _getSegment( self, context, segment ):
        """
            Returns folder instance. Segment can be instance itself or uid
        """
        segment_object = None
        if isInstance( segment, StringType ):
            catalog = getToolByName( context, 'portal_catalog', None )
            if catalog is not None:
                segment_object = catalog.unrestrictedGetObjectByUid( segment, 'isContentStorage' )
        else:
            segment_object = segment

        return segment_object

    def getSubFolderById( self, context, segment=None, id=None ):
        """
            Arguments:

                'context' -- any object through which portal catalog can be acquired.

                'segment' -- nd_uid of root custom segment (folder) or folder itself.

                'id' -- id of department.
        """
        subFolder = None
        if segment is None:
            segment = DefaultSegment( context )

        segment_object = self._getSegment( context, segment )
        if not id or segment_object is None:
            return None

        try:
            subFolder = segment_object[ id ]
        except: # ( AttributeError, KeyError, TypeError ):
            catalog = getToolByName( segment_object, 'portal_catalog', None )
            if catalog is None:
                return None

            query = {}
            query['path'] = segment_object.physical_path() + '%'
            query['implements'] = 'isContentStorage'
            query['id'] = id

            res = catalog.unrestrictedSearch( **query )

            if res and len(res) >= 1:
                subFolder = res[0].getObject()

        return subFolder

    getDepartmentFolder = getSubFolderById

    def getSubFolderByTitle( self, context, segment, title ):
        """
            Arguments:

                'context' -- any object through which portal catalog can be acquired.

                'segment' -- nd_uid of root custom segment (folder) or folder itself.

                'title' -- department title.
        """
        return self.getSubFolderById( context, segment, self.getIdByTitle( title ) )

    def getUserDepartment( self, context, member=None, segment=None ):
        """
            Arguments:

                'context' -- any object through which portal catalog can be acquired.

                'member' -- member object.

                'segment' -- nd_uid of root custom segment (folder) or folder itself.
        """
        if not member:
            membership = getToolByName( context, 'portal_membership', None )
            member = membership.getAuthenticatedMember()

        member_department = member.getMemberDepartment()
        if not member_department:
            return None

        subFolder = self.getSubFolderByTitle( context, segment, member_department )
        return subFolder

    def listCompanies( self ):
        """
            Returns mapping list of companies (id, title), only accepted
        """
        res = []
        for id, value in self.enumerateCompanies():
            res.append( { 'id'      : id, 
                          'postfix' : value[ COMPANY_POSTFIX ], 
                          'name'    : value[ COMPANY_NAME ], 
                          'title'   : value[ COMPANY_TITLES ][0] ,
                        } )
        return res

    def listCompanyIds( self ):
        """
            Returns list of company ids
        """
        return self._data[ COMPANIES ].keys()

    def listCompanyTitles( self ):
        """
            Returns list of company titles, only accepted
        """
        res = []
        for value in self._data[ COMPANIES ].values():
            res.append( value[ COMPANY_TITLES ][0] )
        return res

    def getCompanyId( self, id ):
        """
            Returns a company title by given department id
        """
        department = self._data[ DEPARTMENTS ].get(id, None)
        return department and department[ COMPANY ]
        
    def getCompanyTitle( self, id, name=None ):
        """
            Returns a company title by given id.

            Arguments:

                id -- company id (String)

                name -- request to return short company name (Boolean).
        """
        company = self._data[ COMPANIES ].get(id, '')
        if not company: return None
        return name and company[ COMPANY_NAME ] or company[ COMPANY_TITLES ][0]

    def getCompanyPostfix( self, id ):
        """
            Returns a company postfix by given id
        """
        company = self._data[ COMPANIES ].get(id, '')
        if not company: return None
        return company[ COMPANY_POSTFIX ]

    def getListOfCompanyTitles( self ):
        """
            Returns whole list of company titles
        """
        res = []
        for value in self._data[ COMPANIES ].values():
            for title in value[ COMPANY_TITLES ]:
                if title not in res:
                    res.append( title )
        return res

    def listDepartments( self, company=None, sort=None, no_break=None ):
        """
            Returns mapping list of departments (id, title) with company groups order
        """
        res = []
        if not company or company.lower() == 'all':
            company_ids = self.listCompanyIds()
        else:
            company_ids = company.split(':')

        for id in company_ids:
            if len(company_ids) > 1 and not no_break:
                res.append( { 'id' : None, 'postfix' : None, 'title' : '--- %s ---' % \
                    self.getCompanyTitle( id, name=1 ) } )
            res.extend( self.listDepartmentItems( company=id, sort=sort ) )

        return res

    def listDepartmentItems( self, company, sort=None ):
        """
            Returns mapping list of departments (id, title), only accepted
        """
        res = []

        for id, value in self.enumerateDepartments():
            if company == value[ COMPANY ]:
                postfix = value[ DEPARTMENT_POSTFIX ]
                title = value[ DEPARTMENT_TITLES ][0]
                res.append( { 'id' : id, 'postfix' : postfix, 'title' : title, 'sorting' : '%s.%s' % ( \
                    value[ COMPANY ], title ) } )

        if res and sort:
            res.sort( lambda x, y: cmp( x['sorting'], y['sorting'] ) )
        return res

    def listDepartmentIds( self ):
        """
            Returns list of department ids
        """
        return self._data[ DEPARTMENTS ].keys()

    def listDepartmentTitles( self ):
        """
            Returns list of department titles, only accepted
        """
        res = []
        for company, postfix, titles in self._data[ DEPARTMENTS ].values():
            res.append( titles[0] )
        return res

    def getDepartmentTitle( self, id ):
        """
            Returns a department title by given id
        """
        return self.getTitleById( id )

    def getDepartmentPostfix( self, id ):
        """
            Returns a department postfix by given id
        """
        department = self._data[ DEPARTMENTS ].get(id, '')
        if not department: return None
        return department[ DEPARTMENT_POSTFIX ]

    def getListOfDepartmentTitles( self ):
        """
            Returns whole list of department titles
        """
        res = []
        for company, postfix, titles in self._data[ DEPARTMENTS ].values():
            for title in titles:
                if title not in res:
                    res.append( title )
        return res

    def enumerateCompanies( self ):
        """
            Returns list of company items (id, value)
        """
        return self._data[ COMPANIES ].items()

    def enumerateDepartments( self ):
        """
            Returns list of department items (id, value)
        """
        return self._data[ DEPARTMENTS ].items()

    def IsPredefinedFolder( self, id ):
        return ( id in CustomPredefinedFolder() or id in self.listDepartmentIds() ) and 1 or 0

departmentDictionary = DepartmentDictionary()
