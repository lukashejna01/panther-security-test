from django.contrib.auth.hashers import check_password
from django.db import migrations, models


def flag_initial_passwords(apps, schema_editor):
    """
    Kdo se pořád přihlašuje vygenerovaným heslem, musí si ho při příštím
    přihlášení změnit. Poté se uložená čitelná hesla smažou spolu se sloupcem.
    """
    Employee = apps.get_model('core', 'Employee')
    for employee in Employee.objects.exclude(generated_password='').select_related('user'):
        if employee.user and check_password(employee.generated_password, employee.user.password):
            employee.must_change_password = True
            employee.save(update_fields=['must_change_password'])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_csszsubmission"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="must_change_password",
            field=models.BooleanField(default=False, verbose_name="Musí si změnit heslo"),
        ),
        migrations.RunPython(flag_initial_passwords, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="employee",
            name="generated_password",
        ),
    ]
