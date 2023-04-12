/*leading comment*/
create --only here
or replace package
    /*smile this*/body 
    "test.scheme"."test_package_body" is
begin
    function test_function(
        test_char in varchar2(400 char),
        test_num in integer(10))
    return integer(10) is
        test_add varchar2(400) := q'"babba'robba"';
    begin
        return length(test_add || q'(smile'this)' || test_char || ' and ' || to_char(test_num) || ' pirates');
    end;
end;
/

/*second object for full test*/
create or replace package /*another smile this*/ body 
    "test.scheme_second"."anotner.test_package_body" is
begin
    function test_function(
        test_char in varchar2(400 char),
        test_num in integer(10))
    return integer(10) is
        test_add varchar2(400) := q'{babba'robba}';
    begin
        test_add := test_add || q'(mub'and'moll)';
        test_add := test_add || q'{swallow'n'mummo}';
        test_add := test_add || q'<cmos"s''n'ppermeld>';
        test_add := test_add || q'borabby'bab';
        return length(test_add || q'(smile'this)' || test_char || ' and ' || to_char(test_num) || ' pirates');
    end;
end;

/
