-- Chỉ dùng khi CHƯA tạo dbo.role/dbo.user. Database đã có thì xem README.
USE [master];
GO
IF DB_ID(N'quan_ly_tro') IS NULL
    EXEC(N'CREATE DATABASE [quan_ly_tro];');
GO
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

    IF OBJECT_ID(N'dbo.role', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.[role] (
            role_id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_role PRIMARY KEY,
            role_name VARCHAR(20) NOT NULL CONSTRAINT UQ_role_role_name UNIQUE,
            description NVARCHAR(255) NULL,
            CONSTRAINT CK_role_role_name CHECK (role_name IN ('ADMIN', 'LANDLORD'))
        );
    END;

    IF OBJECT_ID(N'dbo.user', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.[user] (
            user_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_user PRIMARY KEY,
            role_id INT NOT NULL,
            full_name NVARCHAR(100) NOT NULL,
            email VARCHAR(255) COLLATE Latin1_General_100_CI_AS NOT NULL CONSTRAINT UQ_user_email UNIQUE,
            phone VARCHAR(20) NULL,
            password_hash VARCHAR(255) NOT NULL,
            status VARCHAR(20) NOT NULL CONSTRAINT DF_user_status DEFAULT ('ACTIVE'),
            created_at DATETIME2(0) NOT NULL CONSTRAINT DF_user_created_at DEFAULT (SYSUTCDATETIME()),
            updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_user_updated_at DEFAULT (SYSUTCDATETIME()),
            CONSTRAINT FK_user_role FOREIGN KEY (role_id) REFERENCES dbo.[role](role_id),
            CONSTRAINT CK_user_full_name CHECK (LEN(LTRIM(RTRIM(full_name))) > 0),
            CONSTRAINT CK_user_email_not_blank CHECK (LEN(LTRIM(RTRIM(email))) > 0),
            CONSTRAINT CK_user_phone_not_blank CHECK (phone IS NULL OR LEN(LTRIM(RTRIM(phone))) > 0),
            CONSTRAINT CK_user_password_hash_not_blank CHECK (LEN(LTRIM(RTRIM(password_hash))) > 0),
            CONSTRAINT CK_user_status CHECK (status IN ('ACTIVE', 'LOCKED'))
        );
    END;

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.user') AND name = N'UX_user_phone')
        CREATE UNIQUE INDEX UX_user_phone ON dbo.[user](phone) WHERE phone IS NOT NULL;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.user') AND name = N'IX_user_role_id')
        CREATE INDEX IX_user_role_id ON dbo.[user](role_id);

    INSERT INTO dbo.[role] (role_name, description)
    SELECT v.role_name, v.description
    FROM (VALUES ('ADMIN', N'Quản trị hệ thống'), ('LANDLORD', N'Chủ nhà trọ')) AS v(role_name, description)
    WHERE NOT EXISTS (SELECT 1 FROM dbo.[role] r WHERE r.role_name = v.role_name);

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
SELECT role_id, role_name, description FROM dbo.[role];
