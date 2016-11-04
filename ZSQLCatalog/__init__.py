##############################################################################
#
# Copyright (c) 2001 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################

"""ZSQLCatalog product"""

import ZSQLCatalog, CatalogAwareness, CatalogPathAwareness
from ZClasses import createZClassForBase

createZClassForBase( ZSQLCatalog.ZSQLCatalog , globals(), 'ZSQLCatalogBase', 'ZSQLCatalog' )
#createZClassForBase( CatalogAwareness.CatalogAware, globals(), 'CatalogAwareBase', 'CatalogAware' )
#createZClassForBase( CatalogPathAwareness.CatalogPathAware, globals(), 'CatalogPathAwareBase', 'CatalogPathAware' )

def initialize(context):
    context.registerClass(
        ZSQLCatalog.ZSQLCatalog,
        permission='Add ZCatalogs',
        constructors=( ZSQLCatalog.manage_addZSQLCatalogForm, ZSQLCatalog.manage_addZSQLCatalog ),
        icon='www/ZSQLCatalog.gif',
        )

    context.registerHelp()
    context.registerHelpTitle('Zope Help')
