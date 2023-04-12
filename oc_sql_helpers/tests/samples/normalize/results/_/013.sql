CREATE OR REPLACE PACKAGE BODY "TEST.SCHEME".TEST_PACKAGE_BODY IS
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