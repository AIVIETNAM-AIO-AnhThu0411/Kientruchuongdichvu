-- Dừng API trước khi chạy trong SSMS. Chỉ có ADMIN và LANDLORD sau khi thành công.
-- Xóa tài khoản TENANT chưa có dữ liệu liên quan; giữ ADMIN và chuyển OWNER sang LANDLORD.
-- Giữ user_id/mật khẩu của Admin và Chủ trọ. Mọi lỗi đều hoàn tác toàn bộ giao dịch.
-- Kiểm tra các FK trong quan_ly_tro; liên kết ở database/dịch vụ khác cần được kiểm tra riêng.
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

    IF OBJECT_ID(N'dbo.role', N'U') IS NULL OR OBJECT_ID(N'dbo.user', N'U') IS NULL
        THROW 50001, N'Chưa có role/user. Chạy 01_create_role_user.sql trước.', 1;

    IF ISNULL(HAS_PERMS_BY_NAME(DB_NAME(), N'DATABASE', N'VIEW DEFINITION'), 0) <> 1
        THROW 50002, N'Cần quyền VIEW DEFINITION trên quan_ly_tro để kiểm tra liên kết vai trò.', 1;

    -- Khóa bảng vai trò trong lúc cập nhật, tránh phát sinh liên kết mới.
    DECLARE @role_count BIGINT;
    SELECT @role_count = COUNT_BIG(*) FROM dbo.[role] WITH (TABLOCKX, HOLDLOCK);


    -- Người dùng đã yêu cầu bỏ tài khoản TENANT khỏi Auth/User Service.
    -- Chỉ xóa khi tất cả tài khoản TENANT chưa có dữ liệu nghiệp vụ tham chiếu.
    DECLARE @tenant_count BIGINT;
    SELECT @tenant_count = COUNT_BIG(*)
    FROM dbo.[user] u WITH (XLOCK, HOLDLOCK)
    JOIN dbo.[role] r ON r.role_id = u.role_id
    WHERE r.role_name = 'TENANT';

    IF @tenant_count > 0
    BEGIN
        DECLARE @tenant_child_schema SYSNAME, @tenant_child_table SYSNAME, @tenant_fk SYSNAME;
        DECLARE @tenant_join NVARCHAR(MAX), @tenant_query NVARCHAR(MAX);
        DECLARE @tenant_has_reference BIT, @tenant_message NVARCHAR(2048);
        DECLARE tenant_reference_cursor CURSOR LOCAL FAST_FORWARD FOR
            SELECT s.name, t.name, fk.name,
                   STRING_AGG(
                       CONVERT(NVARCHAR(MAX), N'c.' + QUOTENAME(pc.name) + N' = u.' + QUOTENAME(rc.name)),
                       N' AND '
                   ) WITHIN GROUP (ORDER BY fkc.constraint_column_id)
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
            JOIN sys.tables t ON t.object_id = fk.parent_object_id
            JOIN sys.schemas s ON s.schema_id = t.schema_id
            JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
            JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
            WHERE fk.referenced_object_id = OBJECT_ID(N'dbo.user')
              AND NOT (s.name = N'dbo' AND t.name = N'auth_session')
            GROUP BY fk.object_id, s.name, t.name, fk.name;

        OPEN tenant_reference_cursor;
        FETCH NEXT FROM tenant_reference_cursor
            INTO @tenant_child_schema, @tenant_child_table, @tenant_fk, @tenant_join;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @tenant_query = N'SELECT @found = CASE WHEN EXISTS (
                SELECT 1 FROM ' + QUOTENAME(@tenant_child_schema) + N'.' + QUOTENAME(@tenant_child_table)
                + N' c WITH (UPDLOCK, HOLDLOCK)
                JOIN dbo.[user] u ON ' + @tenant_join + N'
                JOIN dbo.[role] r ON r.role_id = u.role_id
                WHERE r.role_name = ''TENANT''
            ) THEN 1 ELSE 0 END;';
            SET @tenant_has_reference = 0;
            EXEC sys.sp_executesql @tenant_query, N'@found BIT OUTPUT', @found = @tenant_has_reference OUTPUT;
            IF @tenant_has_reference = 1
            BEGIN
                SET @tenant_message = N'Không xóa được tài khoản TENANT: còn dữ liệu ở '
                    + QUOTENAME(@tenant_child_schema) + N'.' + QUOTENAME(@tenant_child_table)
                    + N' (FK ' + @tenant_fk + N'). Đã hoàn tác toàn bộ, giữ nguyên tài khoản và dữ liệu.';
                THROW 50006, @tenant_message, 1;
            END;
            FETCH NEXT FROM tenant_reference_cursor
                INTO @tenant_child_schema, @tenant_child_table, @tenant_fk, @tenant_join;
        END;
        CLOSE tenant_reference_cursor;
        DEALLOCATE tenant_reference_cursor;

        -- Bảng nhà trọ cũ có thể đã tạo thiếu FK owner_id -> user_id.
        IF OBJECT_ID(N'dbo.boarding_house', N'U') IS NOT NULL
           AND COL_LENGTH(N'dbo.boarding_house', N'owner_id') IS NOT NULL
        BEGIN
            SET @tenant_has_reference = 0;
            EXEC sys.sp_executesql
                N'SELECT @found = CASE WHEN EXISTS (
                    SELECT 1 FROM dbo.boarding_house b WITH (UPDLOCK, HOLDLOCK)
                    JOIN dbo.[user] u ON u.user_id = b.owner_id
                    JOIN dbo.[role] r ON r.role_id = u.role_id
                    WHERE r.role_name = ''TENANT''
                ) THEN 1 ELSE 0 END;',
                N'@found BIT OUTPUT', @found = @tenant_has_reference OUTPUT;
            IF @tenant_has_reference = 1
                THROW 50007, N'Tài khoản TENANT còn được boarding_house.owner_id tham chiếu. Đã hoàn tác, chưa xóa dữ liệu.', 1;
        END;

        -- Phiên xác thực là dữ liệu kỹ thuật: thu hồi trước khi xóa tài khoản.
        IF OBJECT_ID(N'dbo.auth_session', N'U') IS NOT NULL
            EXEC(N'DELETE s FROM dbo.auth_session s
                   JOIN dbo.[user] u ON u.user_id = s.user_id
                   JOIN dbo.[role] r ON r.role_id = u.role_id
                   WHERE r.role_name = ''TENANT'';');

        DELETE u FROM dbo.[user] u
        JOIN dbo.[role] r ON r.role_id = u.role_id
        WHERE r.role_name = 'TENANT';
    END;

    -- Không tự xóa hoặc cấp quyền Chủ trọ cho tài khoản có vai trò khác.
    IF EXISTS (
        SELECT 1 FROM dbo.[user] u WITH (UPDLOCK, HOLDLOCK)
        JOIN dbo.[role] r ON r.role_id = u.role_id
        WHERE r.role_name NOT IN ('ADMIN', 'LANDLORD', 'OWNER')
    )
    BEGIN
        SELECT u.user_id, u.full_name, u.email, r.role_name, u.status
        FROM dbo.[user] u JOIN dbo.[role] r ON r.role_id = u.role_id
        WHERE r.role_name NOT IN ('ADMIN', 'LANDLORD', 'OWNER');
        THROW 50003, N'Còn tài khoản dùng TENANT hoặc vai trò khác. Chưa thay đổi dữ liệu. Cần xử lý các tài khoản trong kết quả trước; không tự chuyển sang LANDLORD.', 1;
    END;

    -- Chỉ thay CHECK của bộ script này; giữ các ràng buộc khác.
    IF EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.role') AND name = N'CK_role_role_name'
    )
        ALTER TABLE dbo.[role] DROP CONSTRAINT CK_role_role_name;

    -- Thu hồi phiên của tài khoản OWNER trước khi đổi vai trò.
    IF OBJECT_ID(N'dbo.auth_session', N'U') IS NOT NULL
        EXEC(N'DELETE s FROM dbo.auth_session s
               JOIN dbo.[user] u ON u.user_id = s.user_id
               JOIN dbo.[role] r ON r.role_id = u.role_id
               WHERE r.role_name = ''OWNER'';');

    -- Chưa có LANDLORD: đổi tên dòng OWNER, giữ nguyên role_id.
    IF NOT EXISTS (SELECT 1 FROM dbo.[role] WHERE role_name = 'LANDLORD')
        UPDATE dbo.[role] SET role_name = 'LANDLORD', description = N'Chủ trọ'
        WHERE role_name = 'OWNER';

    INSERT INTO dbo.[role] (role_name, description)
    SELECT v.role_name, v.description
    FROM (VALUES ('ADMIN', N'Quản trị hệ thống'), ('LANDLORD', N'Chủ trọ')) v(role_name, description)
    WHERE NOT EXISTS (SELECT 1 FROM dbo.[role] r WHERE r.role_name = v.role_name);

    -- Đã có cả OWNER và LANDLORD: chuyển tài khoản sang LANDLORD đang có.
    UPDATE u SET role_id = new_role.role_id, updated_at = SYSUTCDATETIME()
    FROM dbo.[user] u
    JOIN dbo.[role] old_role ON old_role.role_id = u.role_id AND old_role.role_name = 'OWNER'
    CROSS JOIN dbo.[role] new_role
    WHERE new_role.role_name = 'LANDLORD';

    -- Kiểm tra mọi FK tới role, kể cả FK CASCADE hoặc đang disabled.
    -- Không để DELETE vai trò tự xóa dữ liệu ở các bảng khác.
    DECLARE @child_schema SYSNAME, @child_table SYSNAME, @fk_name SYSNAME;
    DECLARE @join_condition NVARCHAR(MAX), @query NVARCHAR(MAX), @has_reference BIT;
    DECLARE @message NVARCHAR(2048);
    DECLARE role_reference_cursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT s.name, t.name, fk.name,
               STRING_AGG(
                   CONVERT(NVARCHAR(MAX), N'c.' + QUOTENAME(pc.name) + N' = r.' + QUOTENAME(rc.name)),
                   N' AND '
               ) WITHIN GROUP (ORDER BY fkc.constraint_column_id)
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
        JOIN sys.tables t ON t.object_id = fk.parent_object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
        JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
        WHERE fk.referenced_object_id = OBJECT_ID(N'dbo.role')
        GROUP BY fk.object_id, s.name, t.name, fk.name;

    OPEN role_reference_cursor;
    FETCH NEXT FROM role_reference_cursor INTO @child_schema, @child_table, @fk_name, @join_condition;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @query = N'SELECT @found = CASE WHEN EXISTS (
            SELECT 1 FROM ' + QUOTENAME(@child_schema) + N'.' + QUOTENAME(@child_table) + N' c WITH (UPDLOCK, HOLDLOCK)
            JOIN dbo.[role] r ON ' + @join_condition + N'
            WHERE r.role_name NOT IN (''ADMIN'', ''LANDLORD'')
        ) THEN 1 ELSE 0 END;';
        SET @has_reference = 0;
        EXEC sys.sp_executesql @query, N'@found BIT OUTPUT', @found = @has_reference OUTPUT;
        IF @has_reference = 1
        BEGIN
            SET @message = N'Vai trò cũ còn dữ liệu tham chiếu ở ' + QUOTENAME(@child_schema) + N'.'
                + QUOTENAME(@child_table) + N' (FK ' + @fk_name + N'). Đã hoàn tác; cần xử lý liên kết trước.';
            THROW 50004, @message, 1;
        END;
        FETCH NEXT FROM role_reference_cursor INTO @child_schema, @child_table, @fk_name, @join_condition;
    END;
    CLOSE role_reference_cursor;
    DEALLOCATE role_reference_cursor;

    DELETE FROM dbo.[role] WHERE role_name NOT IN ('ADMIN', 'LANDLORD');
    UPDATE dbo.[role] SET description = N'Quản trị hệ thống' WHERE role_name = 'ADMIN';
    UPDATE dbo.[role] SET description = N'Chủ trọ' WHERE role_name = 'LANDLORD';

    ALTER TABLE dbo.[role] WITH CHECK ADD CONSTRAINT CK_role_role_name
        CHECK (role_name IN ('ADMIN', 'LANDLORD'));

    UPDATE dbo.[user] SET created_at = SYSUTCDATETIME() WHERE created_at IS NULL;
    UPDATE dbo.[user] SET updated_at = created_at WHERE updated_at IS NULL;
    SELECT @role_count = COUNT_BIG(*) FROM dbo.[role];
    IF @role_count <> 2
        THROW 50005, N'Bảng role chưa có đúng 2 dòng. Đã hoàn tác.', 1;

    COMMIT TRANSACTION;
    SELECT role_id, role_name, description FROM dbo.[role] ORDER BY role_id;
    SELECT u.user_id, u.full_name, u.email, u.phone, r.role_name, u.status
    FROM dbo.[user] u JOIN dbo.[role] r ON r.role_id = u.role_id ORDER BY u.user_id;
    SELECT @tenant_count AS so_tai_khoan_TENANT_da_xoa;
    PRINT N'Thành công: đã dọn tài khoản TENANT chưa có liên kết, chỉ còn ADMIN và LANDLORD (Chủ trọ).';
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'tenant_reference_cursor') >= 0
        CLOSE tenant_reference_cursor;
    IF CURSOR_STATUS('local', 'tenant_reference_cursor') >= -1
        DEALLOCATE tenant_reference_cursor;
    IF CURSOR_STATUS('local', 'role_reference_cursor') >= 0
        CLOSE role_reference_cursor;
    IF CURSOR_STATUS('local', 'role_reference_cursor') >= -1
        DEALLOCATE role_reference_cursor;
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
