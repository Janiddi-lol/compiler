/* The BX runtime: the procedures that compiled BX programs call. */

#include <stdio.h>
#include <stdint.h>

void __bx_print_int(int64_t x)
{
    printf("%lld\n", (long long) x);
}

/* booleans are passed as 64-bit integers: 0 is false, anything else is true */
void __bx_print_bool(int64_t x)
{
    printf("%s\n", x == 0 ? "false" : "true");
}
