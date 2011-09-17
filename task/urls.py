from django.conf.urls.defaults import patterns, include, url
from django.views.generic import DetailView, ListView, TemplateView
from task.models import Task

urlpatterns = patterns('',
    (r'^$',
        ListView.as_view(
            queryset=Task.objects.all(),
            context_object_name='task_list',
            template_name='task_list.html')),
    (r'^(?P<pk>\d+)/$',
        DetailView.as_view(
            model=Task,
            template_name='task_detail.html')),
    (r'^new/$', 'task.views.new'),
    (r'^new/finish/$',
        TemplateView.as_view(template_name='task_new_finish.html')),
)