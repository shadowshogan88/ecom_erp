from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import LoginForm, RegisterForm

def login_view(request):
    next_url = request.GET.get("next") or reverse("products:home")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect(request.POST.get("next") or next_url)
    else:
        form = LoginForm(request)

    return render(request, "pages/login.html", {"form": form, "next": next_url})


def register_view(request):
    next_url = request.GET.get("next") or reverse("products:home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = user.Role.CUSTOMER
            user.save()
            login(request, user)
            return redirect(request.POST.get("next") or next_url)
    else:
        form = RegisterForm()

    return render(request, "pages/register.html", {"form": form, "next": next_url})


def logout_view(request):
    logout(request)
    return redirect("products:home")
