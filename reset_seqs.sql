DO $$
DECLARE
    seq_name text;
    rec record;
BEGIN
    FOR rec IN 
        SELECT table_name, column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND column_default LIKE 'nextval(%'
    LOOP
        EXECUTE 'SELECT pg_get_serial_sequence(''' || rec.table_name || ''', ''' || rec.column_name || ''')' INTO seq_name;
        IF seq_name IS NOT NULL THEN
            EXECUTE 'SELECT setval(''' || seq_name || ''', COALESCE((SELECT MAX(' || rec.column_name || ') FROM ' || rec.table_name || '), 1), (SELECT MAX(' || rec.column_name || ') IS NOT NULL FROM ' || rec.table_name || '))';
            RAISE NOTICE 'Resetted sequence % for table %', seq_name, rec.table_name;
        END IF;
    END LOOP;
END;
$$;
