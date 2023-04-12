CREATE OR REPLACE PACKAGE BODY "TEST.SCHEME_SECOND"."ANOTNER.TEST_PACKAGE_BODY" IS
BEGIN
    FUNCTION TEST_FUNCTION(
        TEST_CHAR IN VARCHAR2(400 CHAR),
        TEST_NUM IN INTEGER(10))
    RETURN INTEGER(10) IS
        TEST_ADD VARCHAR2(400) := q'{babba'robba}';
    BEGIN
        TEST_ADD := TEST_ADD || q'(mub'and'moll)';
        TEST_ADD := TEST_ADD || q'{swallow'n'mummo}';
        TEST_ADD := TEST_ADD || q'<cmos"s''n'ppermeld>';
        TEST_ADD := TEST_ADD || q'borabby'bab';
        RETURN LENGTH(TEST_ADD || q'(smile'this)' || TEST_CHAR || ' and ' || TO_CHAR(TEST_NUM) || ' pirates');
    END;
END;

/
