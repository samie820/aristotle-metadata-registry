from braces.views import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, get_object_or_404
from django.template.defaultfilters import slugify
from django.views.generic import DetailView, ListView, RedirectView, FormView

from aristotle_mdr import forms as MDRForms
from aristotle_mdr import models as MDR
from aristotle_mdr.perms import user_in_workgroup, user_is_workgroup_manager
from aristotle_mdr.views.utils import workgroup_item_statuses, paginate_sort_opts


class WorkgroupContextMixin:
    workgroup = None

    def get_context_data(self, **kwargs):
        kwargs.update({
            'item': self.workgroup,
            'workgroup': self.workgroup,
            'user_is_admin': user_is_workgroup_manager(self.request.user, self.workgroup),
        })
        return super().get_context_data(**kwargs)

    def check_user_permission(self):
        if not self.workgroup or not user_in_workgroup(self.request.user, self.workgroup):
            raise PermissionDenied


class WorkgroupView(LoginRequiredMixin, WorkgroupContextMixin, DetailView):
    model = MDR.Workgroup
    pk_url_kwarg = 'iid'
    slug_url_kwarg = 'name_slug'

    def get(self, request, *args, **kwargs):
        self.object = self.workgroup = self.get_object()
        slug = self.kwargs.get(self.slug_url_kwarg, None)
        if slug is not None and not slugify(self.object.name).startswith(slug):
            return redirect(self.object.get_absolute_url())
        self.check_user_permission()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        kwargs.update({
            'counts': workgroup_item_statuses(self.object),
            'recent': MDR._concept.objects.filter(
                workgroup=self.object).select_subclasses().order_by('-modified')[:5]
        })
        return super().get_context_data(**kwargs)

    def get_template_names(self):
        return self.object and [self.object.template] or []


class ItemsView(LoginRequiredMixin, WorkgroupContextMixin, ListView):
    template_name = "aristotle_mdr/workgroupItems.html"
    sort_by = None

    def get_paginate_by(self, queryset):
        return self.request.GET.get('pp', 20)

    def get_context_data(self, **kwargs):
        kwargs.update({
            'sort': self.sort_by,
            'select_all_list_queryset_filter': 'workgroup__pk=%s' % self.workgroup.pk
        })
        context = super().get_context_data(**kwargs)
        context['page'] = context.get('page_obj')  # dirty hack for current template
        return context

    def get_queryset(self):
        iid = self.kwargs.get('iid')
        self.sort_by = self.request.GET.get('sort', "mod_desc")
        if self.sort_by not in paginate_sort_opts.keys():
            self.sort_by = "mod_desc"

        self.workgroup = get_object_or_404(MDR.Workgroup, pk=iid)
        self.check_user_permission()
        return MDR._concept.objects.filter(workgroup=iid).select_subclasses().order_by(
            *paginate_sort_opts.get(self.sort_by))


class MembersView(LoginRequiredMixin, WorkgroupContextMixin, DetailView):
    template_name = 'aristotle_mdr/workgroupMembers.html'
    model = MDR.Workgroup
    pk_url_kwarg = 'iid'

    def get_object(self, queryset=None):
        self.workgroup = super().get_object(queryset)
        self.check_user_permission()
        return self.workgroup


class RemoveRoleView(LoginRequiredMixin, WorkgroupContextMixin, RedirectView):
    permanent = False
    pattern_name = 'aristotle:workgroupMembers'

    def get_redirect_url(self, *args, **kwargs):
        iid = self.kwargs.get('iid')
        role = self.kwargs.get('role')
        userid = self.kwargs.get('userid')
        self.workgroup = get_object_or_404(MDR.Workgroup, pk=iid)
        self.check_user_permission()
        user = User.objects.filter(id=userid).first()
        if user:
            self.workgroup.removeRoleFromUser(role, user)
        return super().get_redirect_url(self.workgroup.pk)


class ArchiveView(LoginRequiredMixin, WorkgroupContextMixin, DetailView):
    model = MDR.Workgroup
    pk_url_kwarg = 'iid'
    template_name = 'aristotle_mdr/actions/archive_workgroup.html'

    def get_object(self, queryset=None):
        self.workgroup = super().get_object(queryset)
        self.check_user_permission()
        return self.workgroup

    def post(self, request, *args, **kwargs):
        self.workgroup = self.get_object()
        self.workgroup.archived = not self.workgroup.archived
        self.workgroup.save()
        return HttpResponseRedirect(self.workgroup.get_absolute_url())


class AddMembersView(LoginRequiredMixin, WorkgroupContextMixin, FormView):
    template_name = 'aristotle_mdr/actions/addWorkgroupMember.html'
    form_class = MDRForms.workgroups.AddMembers

    def get_form(self, form_class=None):
        iid = self.kwargs.get('iid')
        self.workgroup = get_object_or_404(MDR.Workgroup, pk=iid)
        self.check_user_permission()
        return super().get_form(form_class)

    def get_context_data(self, **kwargs):
        kwargs.update({
            'role': self.request.GET.get('role')
        })
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        users = form.cleaned_data['users']
        roles = form.cleaned_data['roles']
        for user in users:
            for role in roles:
                self.workgroup.giveRoleToUser(role, user)
        return super().form_valid(form)

    def get_initial(self):
        return {'roles': self.request.GET.getlist('role')}

    def get_success_url(self):
        return reverse("aristotle:workgroupMembers", args=[self.workgroup.pk])


class LeaveView(LoginRequiredMixin, WorkgroupContextMixin, DetailView):
    model = MDR.Workgroup
    pk_url_kwarg = 'iid'
    template_name = 'aristotle_mdr/actions/workgroup_leave.html'

    def get_object(self, queryset=None):
        self.workgroup = super().get_object(queryset)
        self.check_user_permission()
        return self.workgroup

    def post(self, request, *args, **kwargs):
        self.get_object().removeUser(request.user)
        return HttpResponseRedirect(reverse("aristotle:userHome"))
