var update_str = 
'              TABLE bgcolor width cellspacing cellpadding bordercolor bordercolordark #'+
'              TBODY #'+
'              TR align bgcolor valign #'+
'              TH align bgcolor valign #'+
'              TD align bgcolor height colspan nowrap rowspan valign width style #'+
'              FONT size color face style #'+
'              P align width style #'+
'              STRONG #'+
'              OL type start #'+
'              UL type start #'+
'              LI style #'+
'              B #'+
'              I #'+
'              U #'+
'              EM #'+
'              SPAN #';

var not_allowed_inside = { 
              'P'     : ['TD','TR','TH','TABLE'], 
              'FONT'  : ['TD','P','SPAN']
};

var not_nested_tags = {
              'UL'    : ['LI','OL','UL'],
              'OL'    : ['LI','OL','UL'],
              'LI'    : ['LI']
};

var formatting_tags = [
              'FONT','SPAN'
];

var formatting_attrs = {
              'TD'    : ['height','width']
};

var style_attrs = {
              'FONT'  : ['font-size'],
              'TD'    : ['margin','padding','font-size'],
              'P'     : ['font-size','color'],
              'LI'    : ['font-size']
};

var included_attrs = { 
              'TABLE' : [1,'align="center" border=2 style="BORDER-COLLAPSE: collapse"'], 
              'P'     : [0,'class=xxx']
};

/*
'              HTML HEAD TITLE #'+
'              BODY #'+
'              P class id width align height #'+
'              DIV align #'+
'              SPAN #'+
'              A class id href name target #'+
'              STRONG BR B U I EM PRE STRIKE SUB SUP #'+
'              H1 align class id #'+
'              H2 align class id #'+
'              H3 align class id #'+
'              H4 align class id #'+
'              UL class id #'+
'              OL class id start #'+
'              LI class id #'+
'              TABLE align class id bgcolor width border cellspacing cellpadding bordercolor bordercolordark #'+
'              TH class id bgcolor #'+
'              TBODY class id #'+
'              TR class id bgcolor valign align #'+
'              TD class id nowrap rowspan width bgcolor colspan valign align #'+
'              IMG style class id src width align height border hspace vspace alt #'+
'              FONT size color class id face #'+
'              BLOCKQUOTE style #'
*/
