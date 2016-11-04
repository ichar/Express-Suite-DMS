## Script (Python) "document_presentation"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=presentation_level, is_index=None
##title=
##
# $Id: document_presentation.py,v 1.9.10.1 2003/12/16 12:45:15 oevsegneev Exp $

REQUEST = context.REQUEST

if context.meta_type == 'HTMLDocument':
    quest_action=REQUEST.get('document_uid', '')
    quest_email=REQUEST.get('quest_email', '')

    if REQUEST.has_key('is_questionnaire'):
        if REQUEST.has_key('do_quest_action') and quest_action=='':
            message = ( "You must fill action field first" )
            action = 'document_presentation_form'
            return REQUEST.RESPONSE.redirect( context.absolute_url( action=action, message=message, frame='document_frame'))
     
        if quest_email=='':
            message = ( "You must fill email field first" )
            action = 'document_presentation_form'
            return REQUEST.RESPONSE.redirect( context.absolute_url( action=action, message=message, frame='document_frame'))
 
        context.setQuestionnaire( quest_email, quest_action, REQUEST.has_key('do_quest_action'))
    else:
        context.resetQuestionnaire()

context.setIndexDocument( is_index )

try:    presentation_level = int( presentation_level )
except: presentation_level = 0

context.setPresentationLevel( presentation_level )

REQUEST.RESPONSE.redirect( context.absolute_url( action='view' ), status=303 )
