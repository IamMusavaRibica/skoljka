from django.conf.urls.defaults import patterns, include, url
from django.views.generic import DetailView, ListView, TemplateView

from search.views import searchView

urlpatterns = patterns('',
    (r'^([a-zA-Z0-9 ]+)/$', 'search.views.searchView'),
    (r'^$', 'search.views.searchView'),
)