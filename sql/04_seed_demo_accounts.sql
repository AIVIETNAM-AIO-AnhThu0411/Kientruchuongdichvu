-- Dữ liệu THỰC HÀNH: chỉ tạo ADMIN và LANDLORD. Email tồn tại không bị ghi đè.
-- ADMIN: admin@troviet.example / Admin@2026!
-- LANDLORD: chutro@troviet.example / ChuTro@2026!
USE [quan_ly_tro];
GO
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET ARITHABORT ON;
SET NUMERIC_ROUNDABORT OFF;
SET XACT_ABORT ON;
GO
BEGIN TRY
    BEGIN TRANSACTION;
    IF NOT EXISTS (SELECT 1 FROM dbo.[role] WHERE role_name = 'ADMIN')
       OR NOT EXISTS (SELECT 1 FROM dbo.[role] WHERE role_name = 'LANDLORD')
        THROW 50003, N'Thiếu ADMIN/LANDLORD. Chạy 05_upgrade_auth.sql trước.', 1;

    INSERT INTO dbo.[user] (role_id, full_name, email, phone, password_hash, status)
    SELECT r.role_id, v.full_name, v.email, NULL, v.password_hash, 'ACTIVE'
    FROM (VALUES
        ('ADMIN', N'Quản trị viên', 'admin@troviet.example',
         '$argon2id$v=19$m=65536,t=3,p=4$jOGxldG8l3KuI/kqRQOQYQ$uEpxiN7tNk1E4XJFfWytOfbXPMT3G8YKCMtF7EoV0qY'),
        ('LANDLORD', N'Chủ nhà trọ', 'chutro@troviet.example',
         '$argon2id$v=19$m=65536,t=3,p=4$S4s6oYjTG+eN6kYwO8+53g$oPzx6rZ6vxt3fyTAHcBJqFqB2oo6TNF3WrqLP4PPB8I')
    ) AS v(role_name, full_name, email, password_hash)
    JOIN dbo.[role] r ON r.role_name = v.role_name
    WHERE NOT EXISTS (SELECT 1 FROM dbo.[user] u WHERE u.email = v.email);

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
SELECT u.user_id, u.full_name, u.email, r.role_name, u.status
FROM dbo.[user] u JOIN dbo.[role] r ON r.role_id = u.role_id
WHERE r.role_name IN ('ADMIN', 'LANDLORD');
