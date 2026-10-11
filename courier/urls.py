from django.urls import path
from courier.views import auth_views, driver_views, manager_views, courier_views

urlpatterns = [

    path('',            auth_views.index,       name='index'),
    path('login/',      auth_views.login_view,  name='login'),
    path('logout/',     auth_views.logout_view, name='logout'),
    path('offline.html', auth_views.offline_view, name='offline'),
    path('sw.js',       auth_views.sw_view,     name='sw'),

    path('driver/',                                driver_views.dashboard,           name='driver_dashboard'),
    path('driver/delivery-waybill/',               driver_views.delivery_waybill,    name='driver_delivery_waybill'),
    path('driver/delivery-waybill/<int:wid>/',     driver_views.view_delivery_waybill, name='driver_view_delivery_waybill'),
    path('driver/return-waybill/',                 driver_views.return_waybill,      name='driver_return_waybill'),
    path('driver/return-waybill/<int:wid>/',       driver_views.view_return_waybill, name='driver_view_return_waybill'),
    path('driver/input-packages/',                 driver_views.input_packages,      name='driver_input_packages'),
    path('driver/start-session/',                  driver_views.start_session,       name='driver_start_session'),
    path('driver/add-package/',                    driver_views.add_package,         name='driver_add_package'),
    path('driver/remove-package/<int:pid>/',       driver_views.remove_package,      name='driver_remove_package'),
    path('driver/confirm-session/<int:sid>/',      driver_views.confirm_session,     name='driver_confirm_session'),
    path('driver/scan-return-qr/',                 driver_views.scan_return_qr,      name='driver_scan_return_qr'),

    path('manager/',                               manager_views.dashboard,          name='manager_dashboard'),
    path('manager/delivery-waybill/',              manager_views.delivery_waybill,   name='manager_delivery_waybill'),
    path('manager/delivery-waybill/<int:wid>/',    manager_views.view_delivery_waybill, name='manager_view_delivery_waybill'),
    path('manager/return-waybill/',                manager_views.return_waybill,     name='manager_return_waybill'),
    path('manager/return-waybill/<int:wid>/',      manager_views.view_return_waybill, name='manager_view_return_waybill'),
    path('manager/missing-waybill/',               manager_views.missing_waybill,    name='manager_missing_waybill'),
    path('manager/accept-packages/',               manager_views.accept_packages,    name='manager_accept_packages'),
    path('manager/edit-package/<int:pid>/',        manager_views.edit_package,       name='manager_edit_package'),
    path('manager/mark-missing/<int:pid>/',        manager_views.mark_missing,       name='manager_mark_missing'),
    path('manager/confirm-package/<int:pid>/',     manager_views.confirm_package,    name='manager_confirm_package'),
    path('manager/confirm-all/',                   manager_views.confirm_all,        name='manager_confirm_all'),
    path('manager/form-delivery-list/',            manager_views.form_delivery_list, name='manager_form_delivery_list'),
    path('manager/mark-return/<int:pid>/',         manager_views.mark_return,        name='manager_mark_return'),
    path('manager/weekly-export/',                 manager_views.weekly_export,      name='manager_weekly_export'),
    path('manager/qr-generator/',                  manager_views.qr_generator,       name='manager_qr_generator'),
    path('manager/qr/<int:pid>.png',               manager_views.get_qr,             name='manager_get_qr'),
    path('manager/export-qr/',                     manager_views.export_qr,          name='manager_export_qr'),
    path('manager/scan-return-qr/',                manager_views.scan_return_qr,     name='manager_scan_return_qr'),
    path('manager/confirm-return-waybill/',        manager_views.confirm_return_waybill, name='manager_confirm_return_waybill'),
    path('manager/change-delivery-date/<int:pid>/', manager_views.change_delivery_date,  name='manager_change_delivery_date'),

    path('courier/',                               courier_views.dashboard,          name='courier_dashboard'),
    path('courier/delivery-waybill/',              courier_views.delivery_waybill,   name='courier_delivery_waybill'),
    path('courier/mark/<int:pid>/',                courier_views.mark_delivery,      name='courier_mark_delivery'),
    path('courier/scan-qr/',                       courier_views.scan_qr,            name='courier_scan_qr'),
]
