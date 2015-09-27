from django.conf import settings
from django.conf.urls.defaults import patterns, include, url

from libs.string_operations import join_urls

def _make_patterns(*patterns):
    result = []
    shorthands = settings.COMPETITION_URLS
    for competition_id, url_path_prefix in shorthands.iteritems():
        for _regex, view in patterns:
            regex = '^' + join_urls(url_path_prefix, _regex)
            result.append(url(regex, view, {'competition_id': competition_id}))

    for _regex, view in patterns:
        regex = join_urls(r'^competition/(?P<competition_id>\d+)/', _regex)
        result.append(url(regex, view))

    return result

# Competition-related URLs, prefixed with competition/<id>/
_patterns = _make_patterns(
    (r'$', 'homepage'),
    (r'chain/$', 'chain_list'),
    (r'chain/(?P<chain_id>\d+)/$', 'chain_edit'),
    (r'chain/(?P<chain_id>\d+)/overview/$', 'chain_overview'),
    (r'chain/new/$', 'chain_new'),
    (r'notifications/$', 'notifications'),
    (r'notifications/admin/$', 'notifications_admin'),
    (r'registration/$', 'registration'),
    (r'rules/$', 'rules'),
    (r'scoreboard/$', 'scoreboard'),
    (r'task/$', 'task_list'),
    (r'task/(?P<ctask_id>\d+)/$', 'task_detail'),
    (r'team/(?P<team_id>\d+)/$', 'team_detail'),
)

_extra_urls = [
    (r'competition/$', 'competition_list'),
]

urlpatterns = patterns('competition.views', *(_patterns + _extra_urls))
