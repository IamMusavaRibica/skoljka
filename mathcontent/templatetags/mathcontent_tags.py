from django import templateregister = template.Library()@register.inclusion_tag('inc_mathcontent_attachments.html')def mathcontent_attachments(content):    return {'files': content.attachments.all()}