from importlib import import_module

from sqlalchemy.orm.interfaces import MANYTOONE
from sqlalchemy.types import BIGINT, BOOLEAN, BigInteger, Boolean, CHAR, DATE, DATETIME, DECIMAL, Date, DateTime, FLOAT, Float, INT, INTEGER, Integer, NCHAR, NVARCHAR, NUMERIC, Numeric, SMALLINT, SmallInteger, String, TEXT, TIME, Text, Time, Unicode, UnicodeText, VARCHAR
from sqlalchemy import func

from . import generators

RANDOM = object()


class GeneratorRegistry:
    " Fabric of generators. "

    generators = dict()

    def __init__(self):
        self.add_generator([Boolean, BOOLEAN],
                           generators.random_boolean_maker)

        self.add_generator([String, VARCHAR, Unicode, NVARCHAR, NCHAR, CHAR],
                           generators.random_string_maker)

        self.add_generator([Date, DATE],
                           generators.random_date_string_maker)

        self.add_generator([DateTime, DATETIME],
                           generators.random_datetime_string_maker)

        self.add_generator([DECIMAL, Numeric, NUMERIC],
                           generators.random_decimal_maker)

        self.add_generator([Float, FLOAT],
                           generators.random_float_maker)

        self.add_generator([Integer, INTEGER, INT],
                           generators.random_integer_maker)

        self.add_generator([BigInteger, BIGINT],
                           generators.random_big_integer_maker)

        self.add_generator([SmallInteger, SMALLINT],
                           generators.random_small_integer_maker)

        self.add_generator([Text, UnicodeText, TEXT],
                           generators.random_string_maker)

        self.add_generator([Time, TIME],
                           generators.random_time_string_maker)

    def add_generator(self, types, f):
        for cls in types:
            self.generators[cls] = f

    def get(self, cls):
        return self.generators.get(
            cls,
            lambda f: generators.loop(lambda: ''))


class ModelMixer:
    " Generator for model. "

    generators = {}

    def __init__(self, model_class):
        if isinstance(model_class, basestring):
            mod, cls = model_class.rsplit('.', 1)
            mod = import_module(mod)
            model_class = getattr(mod, cls)
        self.mapper = model_class._sa_class_manager.mapper

    def blend(self, mixer, **explicit_values):
        target = self.mapper.class_()

        model_explicit_values = {}
        related_explicit_values = {}
        for key, value in explicit_values.iteritems():
            if '__' in key:
                prefix, _, postfix = key.partition('__')
                params = related_explicit_values.setdefault(prefix, {})
                params[postfix] = value
            else:
                model_explicit_values[key] = value

        self.set_explicit_values(mixer, target, model_explicit_values)
        exclude = model_explicit_values.keys()
        self.set_local_fields(target, mixer, exclude)
        self.set_related_fields(target, mixer, exclude, related_explicit_values=related_explicit_values)
        return target

    def set_explicit_values(self, mixer, target, values):
        for k, v in values.iteritems():

            if v == RANDOM:
                try:
                    column = self.mapper.columns.get(k)
                    v = self.generator_for(mixer.registry, column).next()
                except AttributeError:
                    prop = self.mapper.get_property(k)
                    v = prop.mapper.class_.query.order_by(func.random()).first()

            elif callable(v):
                v = v()

            setattr(target, k, v)

    def set_local_fields(self, target, mixer, exclude):
        columns = [c for c in self.mapper.columns if not c.
                   nullable and not c.foreign_keys and not c.name in exclude]

        for column in columns:
            if column.default:
                v = column.default.execute(mixer.db.session.bind)
            else:
                v = self.generator_for(mixer.registry, column).next()
            setattr(target, column.name, v)

    def set_related_fields(self, target, mixer, exclude, related_explicit_values):
        related_explicit_values = related_explicit_values or dict()
        for prop in self.mapper.iterate_properties:
            if hasattr(prop, 'direction') and prop.direction == MANYTOONE and not prop.key in exclude:
                col = prop.local_remote_pairs[0][0]
                if col.nullable:
                    continue
                related_values = related_explicit_values.get(prop.key, dict())
                value = mixer.blend(prop.mapper.class_, **related_values)
                setattr(target, prop.key, value)
                setattr(target, col.name,
                        prop.mapper.identity_key_from_instance(value)[1][0])

    def generator_for(self, registry, column):
        cls = type(column.type)
        if not column.name in self.generators:
            gen_maker = registry.get(cls)
            generator = gen_maker(column)
            self.generators[column.name] = generator()
        return self.generators[column.name]
