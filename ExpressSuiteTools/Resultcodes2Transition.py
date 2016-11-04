"""
Class for edit 'resultcodes2transition'.

Docflow need information about where to go when task will be finalized with specific result code (
also of more that one task will be finalized with specific result codes).

For this purpose and exists 'Resultcodes2TransitionModel' which provide on the one hand interface for
add/remove/delete records on the other hand inteface for access to information.

Also exists additional classes:

  Resultcodes2TransitionController - controller which takes information from form's request and store it to model

  Resultcodes2Transition - this is container for model and controller

$Id: Resultcodes2Transition.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 10/12/2007 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from Acquisition import Implicit

from Products.CMFCore.utils import getToolByName
from Products.CMFCore.Expression import Expression
from Products.PageTemplates.Expressions import getEngine

from SimpleObjects import Persistent
from Utils import InitializeClass


class Resultcodes2Transition( Persistent ):
    """
        Container for model and controller (View are dtml)
    """
    def __init__( self ):
        Persistent.__init__( self )

    def _initstate( self, mode ):
        """ Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        if getattr( self, 'controller', None ) is None:
            self.controller = Resultcodes2TransitionController()

        return 1

    def setModel( self, model ):
        """
            Initialize model object.

            Arguments:

                'model' -- model (instance of 'Resultcodes2TransitionModel')
        """
        self.model = model
        self.controller.setModel( self.model )


class Resultcodes2TransitionModel( Persistent, Implicit ):
    """
        Class-model for 'resultcodes2transition' table.

        Provide interface for add/change/delete records.

        Contain dictionary 'self.variants' follow format:

        >>> self.variants :=
        >>>  {
        >>>    [id_variant1]:
        >>>      {
        >>>          "python_script": 'content',
        >>>          "transition": [transition],
        >>>          "note": 'note'
        >>>       },
        >>>    [id_variant2]:
        >>>      ...
        >>>  }

        where:
            -- 'id_variant' - are inner unique id.
            -- 'python_script' - python's script results 'true' of 'false'
            -- 'transition ' - the transition which have to be performed, in case of result codes

    """
    error_codes = {
       "double_result_codes": 'Double result codes',
       "all_none": 'All result codes None',
    }

    def __init__( self ):
        Persistent.__init__( self )

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        if getattr( self, 'variants', None ) is None:
            self.variants = {}

        return 1

    def setTaskTemplateContainer( self, taskTemplateContainer ):
        """
            Initialization by task template container.

            Arguments:

            'taskTemplateContainer' -- instance of 'TaskTemplateContainer'
        """
        self.taskTemplateContainer = taskTemplateContainer

    def setCategoryId( self, category_id ):
        """
            Initialization by category id for which this instance of 'Resultcodes2TransitionModel' works.

            Arguments:

                'category_id' -- category id
        """
        self.category_id = category_id

    def modify( self, action, id_variant, value ):
        """
            Interface for modify content ('self.variants').

            Arguments:

                'action' -- action to perfom ['delete' | 'add' | 'change']

                'id_variant' -- id variant for make action

                'value' -- value of variant
        """
        id_variant = int(id_variant)
        if action == 'delete':
            del self.variants[id_variant]
        elif action == 'add_script':
            if value["python_script"] == '': return 'all_none'
            self.variants[id_variant] = value
        elif action == 'change':
            if value["python_script"] == '': return 'all_none'
            self.variants[id_variant] = value
        self._p_changed = 1
        return ''

    def getTransitionByResultCodes( self, result_codes, state ):
        """
            Takes transtion by array of result codes.

            Arguments:

                'result_codes' -- array of result codes

            Result:

                Return transition id if result codes match, or ''
        """
        for id_variant in self.variants.keys():
            # check python script condition
            expression = "python: %s" % self.variants[id_variant]["python_script"]
            condition = Expression(expression)
            error = 0
            try:
                res = condition( getEngine().getContext( {'result_codes': result_codes, 'state': state } ) )
            except:
                error = 1
            # TODO:
            # if error then send email to admin?

            if not error and res:
                return self.variants[id_variant]["transition"]
        return ''

    def getVariantIds( self ):
        """
            Returns array of variants ids
        """
        ids = self.variants.keys()
        ids.sort()
        return ids

    def getVariantById( self, idv ):
        """
            Returns variant by id.

            Arguments:

                'idv' -- id of variant

            Result:

                Returns 'variant'.
        """
        return self.variants[ idv ]

    def getTemplateIds( self, filter=None ):
        """
            Returns template's id which are taken from 'self.taskTemplateContainer'
        """
        return self.taskTemplateContainer.getTaskTemplateIds( filter=filter )

    def getTemplateTitleById( self, template_id ):
        """
            Returns template title by id.

            Arguments:

                'template_id' -- id of template

            Result:

                Returns title of task template (action template).
        """
        return self.taskTemplateContainer.getTaskTemplate( template_id ).toArray()["template_title"]

    def getResultCodesOfTemplate( self, template_id ):
        """
            Returns result codes of template.

            Arguments:

                'template_id' -- id of template

            Result:

                Returns array of result codes of templates
                (which is associated with specific task-brains)
        """
        return self.taskTemplateContainer.taskTemplates[template_id].getResultCodes()

    def getResultCodesOfTemplateByIdTitle( self, template_id ):
        """
            Returns result codes of template in specific format.

            Arguments:

                'template_id' -- id of template

            Result:

                Dictionary follow format:
                { 'id_result_code1': 'title_result_code1', 'id_result_code2': 'title_result_code2', ... }
        """
        arr = {}
        for item in self.taskTemplateContainer.taskTemplates[template_id].getResultCodes():
            arr[item['id']] = item['title']
        return arr

    def getTransitionIds( self ):
        """
            Returns transition of current category.

            Result:

                Return array of transition id

        """
        portal_metadata = getToolByName( self, 'portal_metadata')
        portal_workflow = getToolByName( self, 'portal_workflow')
        wf = portal_metadata.getCategoryById( self.category_id ).Workflow()
        return portal_workflow[wf].transitions.objectIds()

    def getNextVariantId( self ):
        """
            Returns unique id for variant.

            Result:

                Return unique id for variant
        """
        try:
            max_id = max(self.variants.keys())
        except:
            max_id = 0
        return max_id+1

    def getErrorStringById( self, error_id ):
        """
            Return error string by id.

            Arguments:

                'error_id' -- id of error

            Result:

                Return string by error code id (class-attribute 'error_codes')
        """
        return self.error_codes[ error_id ]

    def onDeleteTemplateId( self, template_id ):
        """
            Performs action needed for correct delete template.

            Arguments:

                'template_id' -- template which will be deleted
        """
        for variant_id in self.variants.keys():
            if template_id in self.variants[variant_id]['resultcodes'].keys():
                del self.variants[variant_id]['resultcodes'][template_id]
                # in case, if "resultcodes" == empty, then remove this variant
                if self.variants[variant_id]['resultcodes'] == {}:
                    del self.variants[variant_id]
        self._p_changed = 1


class Resultcodes2TransitionController:
    """
        Class controller for 'Resultcodes2TransitionModel' takes information from request and perform
        actions over model ('Resultcodes2TransitionModel').
    """
    def __init__( self ):
        self.model = None

    def setModel( self, model ):
        """
            Initialization of model.

            Arguments:

                'model' -- model, instance of 'Resultcodes2TransitionModel'
        """
        self.model = model

    def makeActionByRequest( self, REQUEST ):
        """
            Makes actions over model by request.

            Arguments:

                'REQUEST' -- request from form
        """
        action = REQUEST.get('action')
        id_variant = REQUEST.get('id_variant', 0)
        python_script = ''

        if action == 'add_script':
            id_variant = self.model.getNextVariantId()
            python_script = REQUEST.get('python_script', '')
        elif action == 'delete':
            id_variant = REQUEST.get('id_variant')
        elif action == 'change':
            id_variant = REQUEST.get('id_variant')
            python_script = REQUEST.get('python_script', '')

        variant = self.getVariantFromRequest(REQUEST)
        return self.model.modify( action, id_variant, variant )

    def getVariantFromRequest( self, request ):
        """
            Takes 'variant' from request.

            Arguments:

                'request' -- request
        """
        variant = {}
        variant["transition"] = request.get('transition','')
        variant["note"] = request.get('note','')
        variant["python_script"] = request.get('python_script', '')
        variant["resultcodes"] = {}

        for template_id in self.model.getTemplateIds( filter='have_result_codes'):
            select_name = 'resultcode_%s' % template_id
            select_value = request.get( select_name )
            if select_value not in ['','__notexists__']:
                variant["resultcodes"][template_id] = select_value

        return variant
