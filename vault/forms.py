from django import forms
from .models import QuerySnippet


from .sql_validation import validate_sql, SQLSyntaxError

class SnippetForm(forms.ModelForm):
    class Meta:
        model = QuerySnippet
        fields = ["title", "description", "sql_text", "db_type", "tags"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "sql_text": forms.Textarea(attrs={"rows": 12, "spellcheck": "false"}),
        }

    def clean(self):
        cleaned = super().clean()
        sql_text = cleaned.get("sql_text")
        db_type = cleaned.get("db_type")
        try:
            validate_sql(sql_text, db_type)
        except SQLSyntaxError as e:
            self.add_error("sql_text", f"SQL syntax error: {e}")
        return cleaned
