﻿from django import forms
from django.contrib.admin import widgets                                       
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group
from django.utils.translation import ugettext_lazy as _
from userprofile.models import UserProfile

from registration.models import RegistrationProfile

# na temelju django-registration/forms.py RegistrationForm

attrs_dict = {'class': 'required'}

class UserCreationForm(forms.Form):
    username = forms.RegexField(regex=r'^\w+$', max_length=30, widget=forms.TextInput(attrs=attrs_dict), label=_(u'Korisničko ime'),
        help_text=_(u'Molimo koristite oblik <i>iprezime</i> ili <i>imeprezime</i>.'))
    email = forms.EmailField(widget=forms.TextInput(attrs=dict(attrs_dict, maxlength=75)), label=_(u'Email'))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs=attrs_dict, render_value=False), label=_(u'Lozinka'))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs=attrs_dict, render_value=False), label=_(u'Lozinka (ponovno)'))
        
    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists() \
            or Group.objects.filter(name__iexact=username).exists():
            raise forms.ValidationError(_(u'This name is already reserved. Please choose another.'))
        return self.cleaned_data['username']

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_(u'E-mail address already in use. Please choose another.'))
        return self.cleaned_data['email']
        
    def clean(self):
        if 'password1' in self.cleaned_data and 'password2' in self.cleaned_data:
            if self.cleaned_data['password1'] != self.cleaned_data['password2']:
                raise forms.ValidationError(_(u'You must type the same password each time'))
        return self.cleaned_data
    

class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']
        
class UserProfileEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(UserProfileEditForm, self).__init__(*args, **kwargs)
        
        F = self.fields
        
        F['birthday'].widget = widgets.AdminDateWidget()
        field_class = {
            'gender': 'span2',
            'birthday': 'span2',
            'city': 'span2',
            'country': 'span2',
        }
        for k, v in field_class.iteritems():
            F[k].widget.attrs['class'] = v


    class Meta:
        model = UserProfile
        fields = ['gender', 'birthday', 'city', 'country', 'quote', 'website', 'show_hidden_tags']
