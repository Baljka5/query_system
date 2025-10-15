from rest_framework import serializers
from .models import QuerySnippet, classify_sql_kind
from .sql_validation import validate_sql, SQLSyntaxError


class QuerySnippetSerializer(serializers.ModelSerializer):
    # Read-only талбарууд
    tag_list = serializers.ReadOnlyField()
    sql_kind = serializers.ReadOnlyField()  # SELECT / modify / dangerous

    class Meta:
        model = QuerySnippet
        fields = [
            "id",
            "title",
            "description",
            "sql_text",
            "db_type",
            "tags",
            "tag_list",
            "sql_kind",  # ← API-д харуулна
            "created_by",
            "use_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_by",
            "use_count",
            "created_at",
            "updated_at",
            "sql_kind",  # ← client-с шууд өөрчилдөггүй
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # SQL синтакс шалгалт (sqlglot)
        try:
            validate_sql(attrs.get("sql_text"), attrs.get("db_type"))
        except SQLSyntaxError as e:
            raise serializers.ValidationError({"sql_text": f"SQL syntax error: {e}"})
        return attrs

    def create(self, validated_data):
        """
        - created_by-г request-ээс онооно
        - sql_kind-ийг автоматаар тооцоод хадгална
        """
        req = self.context.get("request")
        if req and getattr(req, "user", None) and req.user.is_authenticated:
            validated_data["created_by"] = req.user

        obj = super().create(validated_data)

        # Моделийн save() автоматаар тооцдог байж магадгүй ч
        # энд дахин баталгаажуулж update хийе
        obj.sql_kind = classify_sql_kind(obj.sql_text)
        obj.save(update_fields=["sql_kind"])
        return obj

    def update(self, instance, validated_data):
        """
        UPDATE үед ч sql_kind-ийг дахин тооцно.
        """
        obj = super().update(instance, validated_data)
        obj.sql_kind = classify_sql_kind(obj.sql_text)
        obj.save(update_fields=["sql_kind"])
        return obj
