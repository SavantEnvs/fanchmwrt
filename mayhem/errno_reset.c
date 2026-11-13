/* fritz_cal_extract tests `errno` after strtoul() without clearing it first. Outside afl-fuzz (the
 * Mayhem smoke test, a reproducer run) the AFL runtime's forkserver handshake leaves errno = EBADF,
 * so `-e` fails before the input is opened. Run the (idempotent) handshake here, ahead of the
 * runtime's own unprioritised constructor, then clear errno. */
#include <errno.h>

void __afl_manual_init(void);

__attribute__((constructor(65535))) static void errno_reset(void)
{
	__afl_manual_init();
	errno = 0;
}
