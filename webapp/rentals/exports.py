"""Shared "export this list to Excel" support for the list views in views.py.

ExportXLSXMixin intercepts ?export=xlsx on an existing ListView's GET and
streams an .xlsx of its current (filtered/searched) queryset instead of
rendering HTML — so every list's own search box also narrows what gets
exported, with no separate export-specific filtering logic to keep in sync.
"""
import openpyxl
from django.http import HttpResponse


class ExportXLSXMixin:
    #: list of (header, attr_name_or_callable) — callable receives one object
    export_columns = []
    #: base filename, no extension
    export_filename = "export"

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "xlsx":
            self.object_list = self.get_queryset()
            return self.export_xlsx(self.object_list)
        return super().get(request, *args, **kwargs)

    def export_xlsx(self, queryset):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = self.export_filename[:31] or "Export"
        ws.append([header for header, _ in self.export_columns])

        for obj in queryset:
            row = []
            for _, getter in self.export_columns:
                value = getter(obj) if callable(getter) else getattr(obj, getter, "")
                row.append("" if value is None else str(value))
            ws.append(row)

        for i, _ in enumerate(self.export_columns, start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 20

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{self.export_filename}.xlsx"'
        wb.save(response)
        return response
