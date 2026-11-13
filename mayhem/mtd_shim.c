/*
 * Environment mock for fritz_tffs_nand_read, which talks to a real MTD device through ioctl(). Linked
 * with -Wl,--wrap=ioctl, so only the tool's own ioctl() calls land here. The input file plays the
 * device: MEMGETINFO reports 16 KiB erase blocks / 2 KiB pages over the file (size rounded down to a
 * whole number of erase blocks, as on any real device), MEMREADOOB returns an error-free OOB area whose
 * id/len/rev words mirror the sector's own header, as the tool expects from a healthy device.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <mtd/mtd-user.h>

#define SHIM_ERASESIZE 0x4000
#define SHIM_PAGESIZE 0x800
#define SHIM_OOBSIZE 0x40

int __wrap_ioctl(int fd, unsigned long req, ...)
{
	va_list ap;
	void *arg;

	va_start(ap, req);
	arg = va_arg(ap, void *);
	va_end(ap);

	if (req == MEMGETINFO) {
		struct mtd_info_user *info = arg;
		struct stat st;

		if (fstat(fd, &st))
			return -1;
		memset(info, 0, sizeof(*info));
		info->type = MTD_NANDFLASH;
		info->size = (uint32_t)st.st_size / SHIM_ERASESIZE * SHIM_ERASESIZE;
		info->erasesize = SHIM_ERASESIZE;
		info->writesize = SHIM_PAGESIZE;
		info->oobsize = SHIM_OOBSIZE;
		return 0;
	}

	if (req == MEMREADOOB) {
		struct mtd_oob_buf *oob = arg;
		uint8_t sec[16] = { 0 };

		memset(oob->ptr, 0xff, oob->length);
		if (pread(fd, sec, sizeof(sec), oob->start) == (ssize_t)sizeof(sec) && oob->length >= 14) {
			memcpy(oob->ptr + 0x02, sec + 0x00, 4);
			memcpy(oob->ptr + 0x06, sec + 0x04, 4);
			memcpy(oob->ptr + 0x0a, sec + 0x0c, 4);
		}
		return 0;
	}

	errno = ENOTTY;
	return -1;
}
