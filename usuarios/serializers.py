from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import NombreRol, Rol, Usuario


class PerfilSerializer(serializers.ModelSerializer):
    rol = serializers.SlugRelatedField(slug_field='nombre', read_only=True)

    class Meta:
        model = Usuario
        fields = ['id', 'nombre', 'email', 'rol', 'tipo_conductor', 'telefono', 'creado_en']
        read_only_fields = fields


class RegistroSerializer(serializers.ModelSerializer):
    """Registro público: siempre crea un conductor. El rol no se recibe del cliente."""

    email = serializers.EmailField(max_length=160)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={'input_type': 'password'}
    )
    tipo_conductor = serializers.ChoiceField(choices=Usuario.TipoConductor.choices)

    class Meta:
        model = Usuario
        fields = ['nombre', 'email', 'password', 'tipo_conductor', 'telefono']
        extra_kwargs = {'telefono': {'required': False}}

    def validate_email(self, value):
        email = value.strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Ya existe un usuario con este correo.')
        return email

    def validate(self, attrs):
        # Los validadores de Django (AUTH_PASSWORD_VALIDATORS) comparan la clave con
        # los datos del usuario, por eso se valida con una instancia sin guardar.
        candidato = Usuario(
            email=attrs.get('email', ''),
            nombre=attrs.get('nombre', ''),
        )
        try:
            validate_password(attrs['password'], user=candidato)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        return attrs

    def create(self, validated_data):
        rol, _ = Rol.objects.get_or_create(nombre=NombreRol.CONDUCTOR)
        password = validated_data.pop('password')
        return Usuario.objects.create_user(
            password=password, rol=rol, is_superuser=False, **validated_data
        )

    def to_representation(self, instance):
        return PerfilSerializer(instance, context=self.context).data


class LoginSerializer(TokenObtainPairSerializer):
    """Igual al de SimpleJWT, pero el correo no distingue mayúsculas."""

    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].strip().lower()
        return super().validate(attrs)
