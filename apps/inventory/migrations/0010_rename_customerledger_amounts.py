from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0009_alter_customerledger_options_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='customerledger',
            old_name='old_amount',
            new_name='opening_amount',
        ),
        migrations.RenameField(
            model_name='customerledger',
            old_name='amount',
            new_name='running_amount',
        ),
        migrations.RenameField(
            model_name='customerledger',
            old_name='balance',
            new_name='closing_balance',
        ),
    ]
