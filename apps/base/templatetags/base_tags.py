from django import template
from django.utils.safestring import mark_safe

from search.utils import search_tasks

register = template.Library()

@register.filter
def fix_label_colon(label):
    # TODO: remove this after Django 1.6 (?)
    return label if label[-1] == ":" else label + ":"

@register.inclusion_tag('inc_news_list.html', takes_context=True)
def show_news(context, div_class=None, title=None):
    news = search_tasks(['news'], user=context['user'], no_hidden_check=True)
    news = news.order_by('-id')

    return {
        'news': news,
        'div_class': div_class,
        'title': title,
        'user': context['user'],
    }
