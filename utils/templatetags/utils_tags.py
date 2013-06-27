﻿from django import forms, template
from django.utils.datastructures import SortedDict
from django.utils.safestring import mark_safe

from skoljka.utils.string_operations import G
from skoljka.utils.xss import escape

import copy


register = template.Library()

def encode_email(email):
    a, b = email[::2], email[1::2]
    return a + b[::-1]

@register.simple_tag
def email_link(email, html=''):
    return mark_safe(u'<a href="#" class="imejl" title="Pošalji email" data-address="{0}">{1}</a>'.format(encode_email(email), html))

# G(male, female, gender)
register.simple_tag(G, name='gender')

# TODO: automatically add all user options (?)
# context[GENERATE_URL_TMP_KEYS] = set of all GET keys to be removed in URLs
GENERATE_URL_TMP_KEYS = '_generate_url_tmp_keys'

@register.simple_tag(takes_context=True)
def temporary_get_key(context, *args):
    """
        Marks specific GET keys as temporary. They will be removed from
        URLs generated by generate_url, if not explicitly defined.
    """
    if GENERATE_URL_TMP_KEYS not in context:
        context[GENERATE_URL_TMP_KEYS] = set(args)
    else:
        context[GENERATE_URL_TMP_KEYS] |= set(args)

    return ''

@register.simple_tag(takes_context=True)
def generate_get_query_string(context, *args, **kwargs):
    """
        Generates GET part of URL given keys to remove (*args) and
        key-value pairs to add (**kwargs). Additionally, removes all
        keys specified in context[GENERATE_URL_TMP_KEYS] set.
        (for more info about this set, look at temporary_get_key)
    """

    get = context['request'].GET.copy()
    for key in args:
        if key in get:
            del get[key]
    for key in context.get(GENERATE_URL_TMP_KEYS, []):
        if key in get:
            del get[key]
    for key, value in kwargs.iteritems():
        get[key] = value
    return escape(get.urlencode())

#############################################
# Form splitting/Fieldset templatetag
# http://djangosnippets.org/snippets/1019/
def get_fieldset(parser, token):
    try:
        name, fields, as_, variable_name, from_, form = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError('bad arguments for %r'  % token.split_contents()[0])

    return FieldSetNode(fields.split(','), variable_name, form)

get_fieldset = register.tag(get_fieldset)

class FieldSetNode(template.Node):
    def __init__(self, fields, variable_name, form_variable):
        self.fields = fields
        self.variable_name = variable_name
        self.form_variable = form_variable

    def render(self, context):

        form = template.Variable(self.form_variable).resolve(context)
        new_form = copy.copy(form)
        new_form.fields = SortedDict([(key, value) for key, value in form.fields.items() if key in self.fields])

        context[self.variable_name] = new_form

        return u''

# Form splitting/Fieldset templatetag {END}
#############################################
