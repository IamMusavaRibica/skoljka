# Create your views here.
from django import forms
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from task.models import Task

class newForm(forms.Form):
    name = forms.CharField(min_length=10,max_length=200)
    content = forms.CharField(widget=forms.Textarea)

def new(request):
    no_form = True
    if request.method == 'POST':
        form = newForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            content = form.cleaned_data['content']
            
            x = Task( name=name, content=content )
            x.save()
            
            return HttpResponseRedirect('/task/new/finish/')
    else:
        form = newForm()
    
    return render_to_response('task_new.html', {
        'form': form,
        },
        context_instance=RequestContext(request),
    )
    